"""
智能体节点实现
使用 LangGraph 的节点函数实现各个智能体的逻辑
"""
import asyncio
import time
import json
import random
import logging
from typing import Callable, Dict, Any, Optional, Tuple, List, Awaitable

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from ..core.config import (
    Config,
    PLANNER_SYSTEM_PROMPT,
    VENUE_SEARCHER_SYSTEM_PROMPT,
    SUPPLIER_SEARCHER_SYSTEM_PROMPT,
    PROCESS_SEARCHER_SYSTEM_PROMPT,
)
from ..core.state import AgentState
from ..storage.cache import RedisCache
from ..storage.rag_knowledgebase import CaseStore
from ..storage import external_tools as ET

# 配置日志
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 速率限制识别 ====================

def _is_rate_limit_error(exc: Exception) -> bool:
    """判断异常是否为速率限制（429）"""
    # 1. openai SDK 明确的限流异常（RateLimitError 继承 APIStatusError，status_code==429）
    if OPENAI_AVAILABLE and isinstance(exc, openai.RateLimitError):
        return True
    # 2. 通用 APIStatusError：按 HTTP 状态码判断（其他 API 异常如 401/403 不命中）
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if status == 429:
        return True
    # 3. 兜底：按错误文本判断
    msg = str(exc)
    return "429" in msg or "速率限制" in msg or "rate limit" in msg.lower()


# ==================== 自适应错峰限速器 ====================

class AdaptiveStagger:
    """自适应错峰限速器

    保证两次 LLM 调用之间至少间隔 ``interval`` 秒（错峰派发），把并行搜索
    的瞬时并发尖峰摊平。遇到 429 时乘性增加间隔（快速退避），调用成功时
    加性减小间隔（缓慢恢复吞吐）—— AIMD 思路。

    所有 LLMClient 实例共享同一个限速器，对同一账户的并发请求统一节流。
    """

    def __init__(
        self,
        initial_interval: float = 0.5,
        min_interval: float = 0.2,
        max_interval: float = 4.0,
        recovery_step: float = 0.05,
    ):
        self._interval = initial_interval
        self._min = min_interval
        self._max = max_interval
        self._recovery = recovery_step
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0  # 基于 time.monotonic()

    @property
    def interval(self) -> float:
        """当前错峰间隔（秒），用于日志展示"""
        return self._interval

    async def acquire(self) -> float:
        """获取一个调用许可，返回实际等待的秒数。

        多个并发调用会按到达顺序排队，依次错开 interval 秒发出，
        从而避免同一毫秒打出多个请求触发 429。
        """
        async with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)
        return wait

    def on_success(self) -> None:
        """调用成功：加性减小间隔，缓慢恢复吞吐"""
        self._interval = max(self._min, self._interval - self._recovery)

    def on_rate_limit(self) -> None:
        """遇到 429：乘性增加间隔，并让后续调用立即暂停一个间隔"""
        self._interval = min(self._max, self._interval * 2.0)
        self._next_allowed = max(self._next_allowed, time.monotonic() + self._interval)


class LLMClient:
    """LLM 客户端封装（错峰派发 + 自适应重试 + 流式输出）"""

    # 全局共享限速器：所有实例对同一账户统一节流
    _limiter: Optional[AdaptiveStagger] = None

    def __init__(self, model: str = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("请安装 openai 库: pip install openai")

        self.client = openai.OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_API_BASE,
            max_retries=0,  # 429/退避完全交给本层 AdaptiveStagger，禁用 SDK 内建重试
        )
        self.model = model or Config.SEARCHER_MODEL

    @classmethod
    def _get_limiter(cls) -> AdaptiveStagger:
        if cls._limiter is None:
            cls._limiter = AdaptiveStagger(
                initial_interval=Config.STAGGER_INITIAL_INTERVAL,
                min_interval=Config.STAGGER_MIN_INTERVAL,
                max_interval=Config.STAGGER_MAX_INTERVAL,
                recovery_step=Config.STAGGER_RECOVERY_STEP,
            )
        return cls._limiter

    async def _stream_collect(
        self,
        create_kwargs: Dict[str, Any],
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """在线程中消费同步流式响应，通过队列把 chunk 传回异步事件循环。

        openai SDK 同步客户端在异步上下文中没有原生的流式 await，
        ``create(stream=True)`` 返回同步迭代器。这里用 executor 线程跑生产者，
        用 asyncio.Queue 把每个 chunk 跨线程传回事件循环，
        从而在异步上下文中实现真正的实时流式回调。
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        client = self.client

        def _producer():
            try:
                stream = client.chat.completions.create(**create_kwargs)
                for chunk in stream:
                    queue.put_nowait(("chunk", chunk))
                queue.put_nowait(("done", None))
            except Exception as e:  # noqa: BLE001 - 跨线程把异常传回事件循环
                queue.put_nowait(("error", e))

        loop.run_in_executor(None, _producer)

        parts: list = []
        while True:
            kind, payload = await queue.get()
            if kind == "chunk":
                try:
                    delta = payload.choices[0].delta.content
                except (AttributeError, IndexError):
                    delta = None
                if delta:
                    parts.append(delta)
                    if on_chunk:
                        on_chunk(delta)
            elif kind == "done":
                break
            elif kind == "error":
                raise payload
        return "".join(parts)

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        on_chunk: Optional[Callable[[str], None]] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        """调用 LLM 获取响应（流式输出 + 错峰派发 + 自适应重试）

        Args:
            system_prompt: 系统 Prompt
            user_message: 用户消息
            max_tokens: 最大输出 token 数
            on_chunk: 流式回调，每收到一段文本就调用一次（用于实时输出）
            max_retries: 429 最大重试次数，默认取 Config.LLM_MAX_RETRIES

        Returns:
            LLM 的响应文本
        """
        max_retries = Config.LLM_MAX_RETRIES if max_retries is None else max_retries

        # LLM 缓存命中（仅无流式回调时，如搜索/提取节点；整合节点带 on_chunk 不缓存）
        if on_chunk is None:
            cached = await RedisCache.get_llm(self.model, system_prompt, user_message)
            if cached is not None:
                logger.debug("LLM 缓存命中")
                return cached

        create_kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "stream": True,
        }

        limiter = self._get_limiter()
        last_err: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            # 错峰派发：等待属于本次调用的 slot
            wait = await limiter.acquire()
            if wait > 0:
                logger.debug(f"错峰等待 {wait:.2f}s")

            # 记录本次是否已向外输出过 chunk（决定 429 后能否重试）
            emitted = {"n": 0}

            def _on_chunk(delta: str, _emitted=emitted) -> None:
                _emitted["n"] += 1
                if on_chunk:
                    on_chunk(delta)

            try:
                text = await self._stream_collect(create_kwargs, _on_chunk)
                limiter.on_success()
                if attempt > 0:
                    logger.info(f"重试第 {attempt} 次成功")
                if on_chunk is None and text.strip():
                    # 空/异常响应不缓存，避免坏结果被复用 7 天（text 为空或纯空白时跳过）
                    await RedisCache.set_llm(self.model, system_prompt, user_message, text)
                return text
            except Exception as e:
                if not _is_rate_limit_error(e):
                    # 非限流异常，直接抛出
                    logger.error(f"LLM 调用失败: {e}")
                    raise

                # ---- 429 限流：自适应退避 + 重试 ----
                limiter.on_rate_limit()
                last_err = e

                if emitted["n"] > 0:
                    # 已经实时输出过部分内容，重试会导致重复，直接抛出
                    logger.error("流式输出过程中触发限流，已有部分输出，放弃重试")
                    raise

                if attempt >= max_retries:
                    logger.error(f"达到最大重试次数({max_retries})，放弃: {e}")
                    raise

                delay = min(
                    Config.LLM_RETRY_MAX_DELAY,
                    Config.LLM_RETRY_BASE_DELAY * (2 ** attempt),
                ) + random.uniform(0, 0.5)
                logger.warning(
                    f"触发速率限制(429)，第 {attempt + 1}/{max_retries} 次重试，"
                    f"退避 {delay:.1f}s（当前错峰间隔 {limiter.interval:.2f}s）"
                )
                await asyncio.sleep(delay)
                continue

        # 理论上不会走到这里
        if last_err:
            raise last_err
        raise RuntimeError("LLM 调用失败：未知原因")

    async def _chat_one_with_retry(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Any:
        """单次非流式 LLM 调用（支持 tools），带错峰 + 429 自适应重试。

        返回 assistant message 对象（含 content / tool_calls）。
        每一轮调用都复用 AdaptiveStagger，与流式 chat 共享同一限速器。
        """
        limiter = self._get_limiter()
        max_retries = Config.LLM_MAX_RETRIES

        create_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        loop = asyncio.get_running_loop()
        last_err: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            wait = await limiter.acquire()
            if wait > 0:
                logger.debug(f"错峰等待 {wait:.2f}s")
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(**create_kwargs),
                )
                limiter.on_success()
                return response.choices[0].message
            except Exception as e:
                if not _is_rate_limit_error(e):
                    logger.error(f"LLM 调用失败: {e}")
                    raise
                limiter.on_rate_limit()
                last_err = e
                if attempt >= max_retries:
                    raise
                delay = min(
                    Config.LLM_RETRY_MAX_DELAY,
                    Config.LLM_RETRY_BASE_DELAY * (2 ** attempt),
                ) + random.uniform(0, 0.5)
                logger.warning(
                    f"触发速率限制(429)，第 {attempt + 1}/{max_retries} 次重试，"
                    f"退避 {delay:.1f}s"
                )
                await asyncio.sleep(delay)
                continue

        if last_err:
            raise last_err
        raise RuntimeError("LLM 调用失败：未知原因")

    async def chat_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        max_tokens: int = 4096,
        max_rounds: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        """Function Calling 循环：LLM 自主调用工具，最终返回整理后的文本。

        Args:
            system_prompt: 系统 Prompt
            user_message: 用户消息（含任务描述）
            tools: OpenAI 兼容 function 工具定义列表
            tool_executor: 工具执行回调 (name, args) -> 结果字符串
            max_tokens: 最大输出 token 数
            max_rounds: 最大工具调用轮数，默认 Config.TOOL_MAX_ROUNDS
            temperature: 采样温度

        Returns:
            LLM 整理后的最终文本
        """
        max_rounds = Config.TOOL_MAX_ROUNDS if max_rounds is None else max_rounds

        # LLM 缓存命中（输入一致 → 输出一致）
        cached = await RedisCache.get_llm(self.model, system_prompt, user_message)
        if cached is not None:
            logger.debug("LLM 缓存命中 (chat_with_tools)")
            return cached

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        for round_idx in range(max_rounds):
            assistant_msg = await self._chat_one_with_retry(
                messages, tools=tools, max_tokens=max_tokens, temperature=temperature
            )

            # 转成 dict 回填（OpenAI 兼容端点接受 dict 格式的 assistant 消息）
            assistant_dict: Dict[str, Any] = {
                "role": "assistant",
                "content": assistant_msg.content or "",
            }
            tool_calls = getattr(assistant_msg, "tool_calls", None)
            if tool_calls:
                assistant_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_dict)

            if not tool_calls:
                # 无工具调用，已是最终文本
                logger.info(f"Function Calling 完成（第 {round_idx + 1} 轮，无工具调用）")
                text = assistant_msg.content or ""
                await RedisCache.set_llm(self.model, system_prompt, user_message, text)
                return text

            # 执行所有工具调用，结果以 role=tool 回喂
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                try:
                    logger.info(f"调用工具 {name}({args})")
                    result = await tool_executor(name, args)
                except Exception as e:
                    logger.warning(f"工具 {name} 执行失败: {e}")
                    result = f"工具调用失败: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })

        # 达到 max_rounds，强制要求给出最终结果
        logger.warning(f"达到最大工具调用轮数({max_rounds})，强制生成最终结果")
        messages.append({
            "role": "user",
            "content": "已达到工具调用上限，请基于已获取的信息直接给出最终结果，不要再调用工具。",
        })
        final_msg = await self._chat_one_with_retry(
            messages, tools=None, max_tokens=max_tokens, temperature=temperature
        )
        text = final_msg.content or ""
        await RedisCache.set_llm(self.model, system_prompt, user_message, text)
        return text


# ==================== 搜索 Agent 节点 ====================

async def venue_searcher_node(state: AgentState) -> Dict[str, Any]:
    """
    场地搜索 Agent 节点
    根据用户需求搜索合适的活动场地

    Args:
        state: 当前智能体状态

    Returns:
        仅包含本节点更新的字段（partial update），避免并行节点冲突
    """
    logger.info("【场地搜索 Agent】开始工作...")

    client = LLMClient(model=Config.SEARCHER_MODEL)

    try:
        user_request = state.get("user_request", "")
        extracted_req = state.get("extracted_requirements", {})

        # 构建搜索请求
        search_prompt = f"""
        根据以下用户需求，搜索合适的活动场地：

        【用户原始需求】
        {user_request}

        【提取的结构化需求】
        {extracted_req}

        请调用高德地图搜索工具（maps_text_search）查询真实场地数据，
        基于返回的真实信息筛选并推荐 3-5 个符合要求的场地，包含详细信息。
        不要编造工具未返回的信息。
        """

        # 优先走高德 MCP + Function Calling；失败则降级到纯 LLM 生成
        degraded = False
        if Config.ENABLE_REAL_TOOLS and Config.AMAP_API_KEY:
            try:
                # 整体超时兜底，防止 MCP 连接异常时长时间挂起
                result = await asyncio.wait_for(
                    ET.run_venue_with_amap(
                        client,
                        system_prompt=VENUE_SEARCHER_SYSTEM_PROMPT,
                        user_message=search_prompt,
                        max_tokens=2048,
                    ),
                    timeout=Config.MCP_READ_TIMEOUT + Config.TOOL_TIMEOUT,
                )
            except Exception as e:
                logger.warning(f"高德 MCP 工具失败，降级到纯 LLM 生成: {e}")
                degraded = True
                result = await client.chat(
                    system_prompt=VENUE_SEARCHER_SYSTEM_PROMPT,
                    user_message=search_prompt,
                    max_tokens=2048,
                )
        else:
            degraded = not Config.ENABLE_REAL_TOOLS
            result = await client.chat(
                system_prompt=VENUE_SEARCHER_SYSTEM_PROMPT,
                user_message=search_prompt,
                max_tokens=2048,
            )

        logger.info("【场地搜索 Agent】完成工作")
        msgs = ["【场地搜索】成功找到场地推荐"]
        errs = []
        if degraded:
            errs.append("【场地搜索】高德工具不可用，已降级为 LLM 生成（数据可能非真实）")
        return {
            "venue_result": result,
            "messages": msgs,
            "errors": errs,
        }
    except Exception as e:
        error_msg = f"【场地搜索】失败: {str(e)}"
        logger.error(error_msg)
        return {
            "venue_result": f"场地搜索出错: {str(e)}",
            "errors": [error_msg],
        }


async def supplier_searcher_node(state: AgentState) -> Dict[str, Any]:
    """
    商家搜索 Agent 节点
    搜索活动所需的各类商家和供应商

    Args:
        state: 当前智能体状态

    Returns:
        仅包含本节点更新的字段（partial update），避免并行节点冲突
    """
    logger.info("【商家搜索 Agent】开始工作...")

    client = LLMClient(model=Config.SEARCHER_MODEL)

    try:
        user_request = state.get("user_request", "")
        extracted_req = state.get("extracted_requirements", {})
        city = (extracted_req or {}).get("city") or "北京"

        # 构建搜索请求
        search_prompt = f"""
        根据以下用户需求，搜索活动所需的商家和供应商：

        【用户原始需求】
        {user_request}

        【提取的结构化需求】
        {extracted_req}

        请调用百度地图搜索工具（baidu_poi_search），针对城市「{city}」按类别查询真实商家：
        1. 餐饮商家（酒席、茶歇）
        2. 活动搭建公司（舞台、背景板）
        3. 设备租赁商（音响、灯光、LED屏）
        4. 摄影摄像服务
        5. 礼品定制商（可选）

        每个类别可多次调用工具查询，最终每类推荐 2-3 家优质商家，包含服务内容和联系方式。
        不要编造工具未返回的信息；若某类无结果，请如实说明。
        """

        # 优先走百度 POI + Function Calling；失败则降级
        degraded = False
        if Config.ENABLE_REAL_TOOLS and Config.BAIDU_MAP_AK:
            try:
                result = await client.chat_with_tools(
                    system_prompt=SUPPLIER_SEARCHER_SYSTEM_PROMPT,
                    user_message=search_prompt,
                    tools=ET.to_provider_tools(["baidu_poi_search"]),
                    tool_executor=ET.dispatch_tool,
                    max_tokens=2048,
                )
            except Exception as e:
                logger.warning(f"百度 POI 工具失败，降级到纯 LLM 生成: {e}")
                degraded = True
                result = await client.chat(
                    system_prompt=SUPPLIER_SEARCHER_SYSTEM_PROMPT,
                    user_message=search_prompt,
                    max_tokens=2048,
                )
        else:
            degraded = not Config.ENABLE_REAL_TOOLS
            result = await client.chat(
                system_prompt=SUPPLIER_SEARCHER_SYSTEM_PROMPT,
                user_message=search_prompt,
                max_tokens=2048,
            )

        logger.info("【商家搜索 Agent】完成工作")
        msgs = ["【商家搜索】成功找到商家推荐"]
        errs = []
        if degraded:
            errs.append("【商家搜索】百度工具不可用，已降级为 LLM 生成（数据可能非真实）")
        return {
            "supplier_result": result,
            "messages": msgs,
            "errors": errs,
        }
    except Exception as e:
        error_msg = f"【商家搜索】失败: {str(e)}"
        logger.error(error_msg)
        return {
            "supplier_result": f"商家搜索出错: {str(e)}",
            "errors": [error_msg],
        }


async def process_searcher_node(state: AgentState) -> Dict[str, Any]:
    """
    流程参考搜索 Agent 节点
    检索相似活动案例和流程模板

    Args:
        state: 当前智能体状态

    Returns:
        仅包含本节点更新的字段（partial update），避免并行节点冲突
    """
    logger.info("【流程参考搜索 Agent】开始工作...")

    client = LLMClient(model=Config.SEARCHER_MODEL)

    try:
        user_request = state.get("user_request", "")
        extracted_req = state.get("extracted_requirements", {}) or {}

        # ===== 1. RAG 优先：检索知识库相似案例（同城 + 人数区间过滤）=====
        rag_cases = []
        if Config.ENABLE_RAG:
            try:
                query = CaseStore.build_embed_text(extracted_req, user_request)
                rag_cases = await CaseStore.search_cases(
                    query,
                    city=extracted_req.get("city"),
                    attendee_count=extracted_req.get("attendee_count"),
                )
            except Exception as e:
                logger.warning(f"RAG 检索失败，走博查兜底: {e}")

        if rag_cases:
            # RAG 命中：跳过博查，把相似案例喂给 LLM 整理
            case_text = "\n\n".join(
                f"【案例{i+1}】{c[0].get('activity_type','')} {c[0].get('city','')} "
                f"{c[0].get('attendee_count','')}人 相似度{c[1]:.2f}\n"
                f"{c[0].get('plan_text','')[:1500]}"
                for i, c in enumerate(rag_cases[:Config.KB_TOP_K])
            )
            rag_prompt = f"""
            根据以下用户需求，参考知识库中的相似历史案例，整理活动流程参考：

            【用户原始需求】
            {user_request}

            【提取的结构化需求】
            {extracted_req}

            【知识库相似案例】
            {case_text}

            请基于以上案例整理：
            1. 推荐的相似活动案例
            2. 标准流程模板
            3. 关键成功要素
            4. 常见问题和避坑指南
            5. 行业标准和最佳实践

            信息不足时如实说明，不要编造。
            """
            result = await client.chat(
                system_prompt=PROCESS_SEARCHER_SYSTEM_PROMPT,
                user_message=rag_prompt,
                max_tokens=2048,
            )
            logger.info(f"【流程参考搜索】命中知识库 {len(rag_cases)} 条案例，跳过博查")
            return {
                "process_result": result,
                "messages": [f"【流程参考搜索】命中知识库 {len(rag_cases)} 条相似案例"],
                "errors": [],
            }

        # ===== 2. 未命中 → 博查 / LLM 兜底 =====
        # 构建搜索请求
        search_prompt = f"""
        根据以下用户需求，检索相似的活动案例和流程模板：

        【用户原始需求】
        {user_request}

        【提取的结构化需求】
        {extracted_req}

        请调用博查 AI 搜索工具（bocha_search）查询真实的活动策划攻略和案例，
        然后基于搜索结果整理：
        1. 推荐的相似活动案例（3-5个，包含相似度评分）
        2. 标准流程模板
        3. 关键成功要素
        4. 常见问题和避坑指南
        5. 行业标准和最佳实践

        不要编造搜索未返回的信息。
        """

        # 优先走博查 + Function Calling；失败则降级
        degraded = False
        if Config.ENABLE_REAL_TOOLS and Config.BOCHA_API_KEY:
            try:
                result = await client.chat_with_tools(
                    system_prompt=PROCESS_SEARCHER_SYSTEM_PROMPT,
                    user_message=search_prompt,
                    tools=ET.to_provider_tools(["bocha_search"]),
                    tool_executor=ET.dispatch_tool,
                    max_tokens=2048,
                )
            except Exception as e:
                logger.warning(f"博查工具失败，降级到纯 LLM 生成: {e}")
                degraded = True
                result = await client.chat(
                    system_prompt=PROCESS_SEARCHER_SYSTEM_PROMPT,
                    user_message=search_prompt,
                    max_tokens=2048,
                )
        else:
            degraded = not Config.ENABLE_REAL_TOOLS
            result = await client.chat(
                system_prompt=PROCESS_SEARCHER_SYSTEM_PROMPT,
                user_message=search_prompt,
                max_tokens=2048,
            )

        logger.info("【流程参考搜索 Agent】完成工作")
        msgs = ["【流程参考搜索】成功找到案例和流程模板"]
        errs = []
        if degraded:
            errs.append("【流程参考搜索】博查工具不可用，已降级为 LLM 生成（数据可能非真实）")
        return {
            "process_result": result,
            "messages": msgs,
            "errors": errs,
        }
    except Exception as e:
        error_msg = f"【流程参考搜索】失败: {str(e)}"
        logger.error(error_msg)
        return {
            "process_result": f"流程参考搜索出错: {str(e)}",
            "errors": [error_msg],
        }


# ==================== Planner Agent 节点 ====================

async def requirement_extractor_node(state: AgentState) -> Dict[str, Any]:
    """
    Planner Agent - 需求提取节点
    从用户自然语言中提取结构化需求

    Args:
        state: 当前智能体状态

    Returns:
        仅包含本节点更新的字段（partial update）
    """
    logger.info("【Planner Agent】开始提取需求...")

    client = LLMClient(model=Config.PLANNER_MODEL)

    try:
        user_request = state.get("user_request", "")

        # 构建需求提取请求
        extract_prompt = f"""
        请从以下用户描述中提取结构化的活动需求信息：

        【用户描述】
        {user_request}

        请以 JSON 格式提取以下信息：
        {{
            "activity_type": "活动类型（年会/发布会/培训会/答谢会等）",
            "theme": "活动主题（如有）",
            "attendee_count": 参与人数（数字），
            "budget": 预算金额（数字，单位：元），
            "city": "城市",
            "preferred_area": "偏好区域（如有）",
            "time": "活动时间（如有）",
            "duration": "活动时长（如有）",
            "special_requirements": ["特殊需求列表"]
        }}

        如果某项信息未提供，请填 null 或空列表。
        只返回 JSON，不要有其他文字。
        """

        result = await client.chat(
            system_prompt="你是活动需求提取专家，擅长从自然语言中提取结构化信息。请以标准 JSON 格式输出结果。",
            user_message=extract_prompt,
            max_tokens=4096  # glm-4.6v 带推理，1024 会被 reasoning_content 耗尽致 JSON 截断
        )

        # 解析 JSON 结果 + pydantic 校验（解析失败时带纠错提示自动重试一次）
        import json
        from ..core.models import Requirements
        from pydantic import ValidationError

        def _parse_extract(text: str):
            """从 LLM 输出解析出合法需求 JSON，返回 (Requirements 实例, 异常或 None)"""
            try:
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return Requirements.model_validate(json.loads(text)), None
            except (json.JSONDecodeError, ValidationError) as e:
                return None, e

        parsed, err = _parse_extract(result)

        # JSON 解析失败（含空响应）：带纠错提示重试一次。
        # 纠错提示拼在 user_message 尾部，构成新缓存键，避免命中缓存里的坏结果。
        if err is not None and isinstance(err, json.JSONDecodeError):
            logger.warning(f"需求提取 JSON 解析失败({err})，带纠错提示重试一次")
            retry_result = await client.chat(
                system_prompt="你是活动需求提取专家，擅长从自然语言中提取结构化信息。请以标准 JSON 格式输出结果。",
                user_message=extract_prompt
                + "\n\n【注意】你上一次的输出不是合法 JSON。请只输出一个合法的 JSON 对象，不要包含任何其他文字、代码围栏或注释。",
                max_tokens=4096,
            )
            parsed, err = _parse_extract(retry_result)

        if parsed is not None:
            logger.info("【Planner Agent】需求提取完成")
            return {
                "extracted_requirements": parsed.model_dump(),
                "messages": [
                    f"【需求提取】成功提取需求: "
                    f"{parsed.activity_type or '未知'} - "
                    f"{parsed.attendee_count or '未知'}人"
                ],
            }

        # 重试后仍失败：降级兜底（保留原始输出便于排查）
        if isinstance(err, json.JSONDecodeError):
            logger.warning(f"需求提取 JSON 解析失败: {err}，使用原始结果")
            return {
                "extracted_requirements": {"raw_extract": result},
                "errors": [f"需求提取 JSON 解析失败: {str(err)}"],
            }
        # 校验失败：字段校验不过（JSON 合法但值非法）
        logger.warning(f"需求提取校验失败: {err}")
        return {
            "extracted_requirements": {
                "raw_extract": result,
                "validation_errors": err.errors(),
            },
            "errors": [f"需求提取字段校验失败: {err.errors()}"],
        }

    except Exception as e:
        error_msg = f"【需求提取】失败: {str(e)}"
        logger.error(error_msg)
        return {
            "extracted_requirements": None,
            "errors": [error_msg],
        }


async def integrator_node(state: AgentState) -> Dict[str, Any]:
    """
    Planner Agent - 方案整合生成节点
    汇总三类搜索结果，生成完整的活动策划方案

    Args:
        state: 当前智能体状态

    Returns:
        仅包含本节点更新的字段（partial update）
    """
    logger.info("【Planner Agent】开始整合方案...")

    client = LLMClient(model=Config.PLANNER_MODEL)

    try:
        user_request = state.get("user_request", "")
        extracted_req = state.get("extracted_requirements", {})
        venue_result = state.get("venue_result", "暂无场地信息")
        supplier_result = state.get("supplier_result", "暂无商家信息")
        process_result = state.get("process_result", "暂无流程参考")

        # 构建整合请求
        integration_prompt = f"""
        根据以下三类搜索结果，生成完整的活动策划方案：

        【用户原始需求】
        {user_request}

        【提取的结构化需求】
        {extracted_req}

        【场地搜索结果】
        {venue_result}

        【商家搜索结果】
        {supplier_result}

        【流程参考搜索结果】
        {process_result}

        请生成完整的活动策划方案，包含以下内容：
        1. 活动概述（主题、目标、时间、地点）
        2. 详细流程安排（时间轴）
        3. 场地配置方案
        4. 商家资源配置
        5. 预算明细表（需控制在用户预算范围内）
        6. 任务清单和负责人
        7. 风险提示和注意事项

        方案要结构清晰、逻辑连贯、可执行。
        """

        # 流式输出：优先推入 SSE 队列（API），否则按配置打印到控制台（CLI）
        stream_queue = state.get("stream_queue")
        console_output = state.get("console_output", Config.ENABLE_STREAM_OUTPUT)
        streamed = False
        on_chunk: Optional[Callable[[str], None]] = None

        if stream_queue is not None:
            # 后端 API SSE 模式：chunk 推入 asyncio.Queue，由 api.py 转发给客户端
            def _queue_chunk(delta: str) -> None:
                try:
                    stream_queue.put_nowait(("chunk", delta))
                except Exception:
                    pass

            on_chunk = _queue_chunk
            streamed = True
        elif console_output:
            # CLI 模式：方案实时打印到控制台（提升体感速度）
            print("\n" + "=" * 70)
            print("【活动策划方案】（实时生成中...）")
            print("=" * 70)
            streamed = True

            def _print_chunk(delta: str) -> None:
                print(delta, end="", flush=True)

            on_chunk = _print_chunk

        try:
            result = await client.chat(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_message=integration_prompt,
                max_tokens=8192,
                on_chunk=on_chunk,
            )
        finally:
            if streamed and stream_queue is None:
                print("\n" + "=" * 70)
            if stream_queue is not None:
                # 结束哨兵：让 SSE 生成器知道方案已生成完毕
                try:
                    stream_queue.put_nowait(("done", None))
                except Exception:
                    pass

        logger.info("【Planner Agent】方案整合完成")
        return {
            "final_plan": result,
            "plan_streamed": streamed,
            "messages": ["【方案生成】成功生成完整策划方案"],
        }
    except Exception as e:
        error_msg = f"【方案整合】失败: {str(e)}"
        logger.error(error_msg)
        return {
            "final_plan": f"方案生成出错: {str(e)}",
            "plan_streamed": False,
            "errors": [error_msg],
        }


def log_state(state: AgentState, node_name: str):
    """打印当前状态（用于调试）"""
    print(f"\n{'='*50}")
    print(f"节点: {node_name}")
    print(f"{'='*50}")
    print(f"用户请求: {state.get('user_request', '')[:100]}...")
    print(f"提取的需求: {state.get('extracted_requirements', '未提取')}")
    print(f"场地结果: {'已获取' if state.get('venue_result') else '未获取'}")
    print(f"商家结果: {'已获取' if state.get('supplier_result') else '未获取'}")
    print(f"流程结果: {'已获取' if state.get('process_result') else '未获取'}")
    print(f"最终方案: {'已生成' if state.get('final_plan') else '未生成'}")
    print(f"消息数: {len(state.get('messages', []))}")
    print(f"错误数: {len(state.get('errors', []))}")
    print(f"{'='*50}\n")