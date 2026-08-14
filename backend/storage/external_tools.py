"""
外部工具接入：百度地图 POI / 博查 AI 搜索 / 高德 MCP

- 百度 POI、博查：REST + Function Calling
- 高德：MCP 远程 SSE，工具加载后同样走 Function Calling
所有工具调用失败时由各搜索节点降级到纯 LLM 生成。

工具定义用 provider 无关的 ToolDef（纯 JSON Schema）统一注册（见 _TOOLS），
到调用边界才由 to_provider_tools() 转成 OpenAI 兼容 function calling 格式
（智谱 / 通义 / DeepSeek 等均收此格式）。新增工具只需在注册表加一行。
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

import httpx

from ..core.config import Config
from .cache import RedisCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDef:
    """一个外部工具的统一描述（与具体模型 API 无关）。

    parameters 直接存 JSON-Schema 本体（不含 {"type":"function","function":{...}} 包装），
    由 to_provider_tools() 在调用边界包装成 OpenAI 兼容格式。
    """

    name: str
    description: str
    parameters: Dict[str, Any]
    # (name, args) -> 结果字符串；name 由分派器校验，静态工具可忽略
    executor: Callable[[str, Dict[str, Any]], Awaitable[str]]


# ==================== 百度地图 POI（商家搜索）====================

async def baidu_poi_search(query: str, region: str, page_size: int = 10) -> str:
    """调用百度地图 Place API 检索 POI，返回精简后的 JSON 字符串（带工具缓存）。"""
    args = {"query": query, "region": region, "page_size": page_size}
    cached = await RedisCache.get_tool("baidu_poi_search", args)
    if cached:
        return cached

    params = {
        "query": query,
        "region": region,
        "page_size": min(page_size, 20),
        "output": "json",
        "ak": Config.BAIDU_MAP_AK,
    }
    async with httpx.AsyncClient(timeout=Config.TOOL_TIMEOUT) as client:
        resp = await client.get(Config.BAIDU_PLACE_ENDPOINT, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != 0:
        logger.warning(f"百度 POI 返回异常: {data.get('message')}")
        return json.dumps({"error": data.get("message", "未知错误"), "results": []},
                          ensure_ascii=False)

    results = []
    for r in (data.get("results") or [])[:page_size]:
        results.append({
            "name": r.get("name"),
            "address": r.get("address"),
            "telephone": r.get("telephone"),
            "lat": (r.get("location") or {}).get("lat"),
            "lng": (r.get("location") or {}).get("lng"),
        })
    result_str = json.dumps(
        {"query": query, "count": len(results), "results": results}, ensure_ascii=False
    )
    await RedisCache.set_tool("baidu_poi_search", args, result_str)
    return result_str


async def _baidu_executor(name: str, args: Dict[str, Any]) -> str:
    """百度 POI 参数映射执行器（name 由统一分派器校验，忽略）"""
    return await baidu_poi_search(
        query=args["query"],
        region=args["region"],
        page_size=args.get("page_size", 10),
    )


# ==================== 博查 AI 搜索（流程参考）====================

async def bocha_search(query: str, count: int = 8) -> str:
    """调用博查 AI 搜索，返回汇总文本 + 参考链接的字符串（带工具缓存）。"""
    args = {"query": query, "count": count}
    cached = await RedisCache.get_tool("bocha_search", args)
    if cached:
        return cached

    headers = {
        "Authorization": f"Bearer {Config.BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"query": query, "summary": True, "count": count}
    async with httpx.AsyncClient(timeout=Config.TOOL_TIMEOUT) as client:
        resp = await client.post(Config.BOCHA_ENDPOINT, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    # 博查返回结构存在差异，做防御性提取
    code = data.get("code")
    if code not in (200, "200", 0, "0"):
        logger.warning(f"博查返回异常: {data.get('msg') or data.get('message')}")
        return json.dumps({"error": data.get("msg") or data.get("message", "未知错误")},
                          ensure_ascii=False)

    d = data.get("data") or {}
    parts: List[str] = []

    # AI 汇总文本
    summary = d.get("summary") or d.get("text")
    if summary:
        parts.append(f"【AI 攻略摘要】\n{summary}")

    # 参考网页
    web_pages = (d.get("webPages") or {}).get("value") or d.get("webPages") or []
    if web_pages:
        parts.append("【参考网页】")
        for i, w in enumerate(web_pages[:count], 1):
            title = w.get("name") or w.get("title")
            url = w.get("url") or w.get("link")
            snip = w.get("summary") or w.get("snippet") or w.get("abstract")
            parts.append(f"{i}. {title}\n   链接: {url}\n   摘要: {snip}")

    if not parts:
        # 兜底：原样返回 data
        parts.append(json.dumps(d, ensure_ascii=False)[:2000])

    result_str = "\n\n".join(parts)
    await RedisCache.set_tool("bocha_search", args, result_str)
    return result_str


async def _bocha_executor(name: str, args: Dict[str, Any]) -> str:
    """博查搜索参数映射执行器（name 由统一分派器校验，忽略）"""
    return await bocha_search(query=args["query"], count=args.get("count", 8))


# ==================== 统一注册表（provider 无关工具定义）====================

# 单一事实来源：工具名 / schema / 执行器绑定一处，缓存 key 与提示词复用同一名字。
# 高德 MCP 工具是会话内动态加载的，不在此静态注册表中（见下方 AMap 段）。
_TOOLS: Dict[str, ToolDef] = {
    "baidu_poi_search": ToolDef(
        name="baidu_poi_search",
        description=(
            "通过百度地图搜索指定城市和类别的商家/POI，返回名称、地址、电话。"
            "用于查找活动所需的餐饮、活动搭建、设备租赁、摄影摄像、礼品定制等商家。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "搜索关键词，如 '餐饮'、'活动搭建'、'设备租赁'、'摄影摄像'"},
                "region": {"type": "string", "description": "城市名，如 '北京'、'上海'"},
                "page_size": {"type": "integer", "description": "返回数量，默认 10", "default": 10},
            },
            "required": ["query", "region"],
        },
        executor=_baidu_executor,
    ),
    "bocha_search": ToolDef(
        name="bocha_search",
        description=(
            "通过博查 AI 搜索获取活动策划相关的流程方案、案例、成功要素、避坑指南等"
            "文本攻略。返回 AI 汇总文本与参考网页。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "搜索查询词，如 '500人年会 流程方案 模板 成功要素'"},
                "count": {"type": "integer", "description": "参考网页数量，默认 8", "default": 8},
            },
            "required": ["query"],
        },
        executor=_bocha_executor,
    ),
}


def to_provider_tools(names: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """把注册表工具转换为 OpenAI 兼容 function calling 格式。

    Args:
        names: 只返回指定工具（None 返回全部）。各搜索节点按需限定自己暴露的工具集；
               传入未注册的工具名立即抛 ValueError（fail-fast）。

    换模型（如通义 / DeepSeek / OpenAI）时只改这里，工具定义不动。
    """
    selected = list(names) if names is not None else list(_TOOLS.keys())
    for n in selected:
        if n not in _TOOLS:
            raise ValueError(f"未注册的工具: {n}")
    return [
        {
            "type": "function",
            "function": {
                "name": _TOOLS[n].name,
                "description": _TOOLS[n].description,
                "parameters": _TOOLS[n].parameters,
            },
        }
        for n in selected
    ]


async def dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    """统一工具分派器：按名查注册表执行；未知工具返回错误串（让 LLM 自纠，不抛异常）。"""
    td = _TOOLS.get(name)
    if td is None:
        return f"未知工具: {name}"
    return await td.executor(name, args)


# ==================== 高德 MCP（场地搜索，动态工具，不走静态注册表）====================

# 场地搜索只暴露这几个工具，避免 LLM 调到无关工具
_AMAP_ALLOWED_TOOLS = {"maps_text_search", "maps_around_search", "maps_geo"}


async def _load_amap_tools(session) -> List[Dict[str, Any]]:
    """从高德 MCP 会话加载工具定义，转为 OpenAI 兼容 function calling 格式。"""
    tools_result = await session.list_tools()
    openai_tools: List[Dict[str, Any]] = []
    for t in tools_result.tools:
        if t.name not in _AMAP_ALLOWED_TOOLS:
            continue
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema or {"type": "object", "properties": {}},
            },
        })
    if not openai_tools:
        raise RuntimeError("高德 MCP 未返回可用工具，请检查 API Key 与端点")
    logger.info(f"高德 MCP 加载工具: {[t['function']['name'] for t in openai_tools]}")
    return openai_tools


def _make_amap_executor(session) -> Callable[[str, Dict[str, Any]], Awaitable[str]]:
    """构造高德 MCP 工具执行器：调用 session.call_tool 并提取文本（带工具缓存）。"""
    async def executor(name: str, args: Dict[str, Any]) -> str:
        logger.info(f"调用高德 MCP 工具 {name}({args})")
        cache_name = f"amap:{name}"
        cached = await RedisCache.get_tool(cache_name, args)
        if cached:
            return cached
        result = await session.call_tool(name, args)
        texts: List[str] = []
        for c in (result.content or []):
            text = getattr(c, "text", None)
            if text:
                texts.append(text)
            else:
                texts.append(str(c))
        text = "\n".join(texts) or "(空结果)"
        await RedisCache.set_tool(cache_name, args, text)
        return text

    return executor


async def run_venue_with_amap(client, system_prompt: str, user_message: str,
                              max_tokens: int = 2048) -> str:
    """连接高德 MCP，加载工具，跑 Function Calling 循环。

    client: LLMClient 实例
    """
    # 惰性导入，避免未安装 mcp 时整个模块不可用
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    url = f"{Config.AMAP_MCP_URL}?key={Config.AMAP_API_KEY}"
    logger.info(f"连接高德 MCP: {Config.AMAP_MCP_URL}")

    # 连接超时 + 读超时，避免 MCP SSE 连接挂死拖慢降级
    async with sse_client(
        url,
        timeout=Config.TOOL_TIMEOUT,
        sse_read_timeout=Config.MCP_READ_TIMEOUT,
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await _load_amap_tools(session)
            executor = _make_amap_executor(session)
            return await client.chat_with_tools(
                system_prompt=system_prompt,
                user_message=user_message,
                tools=tools,
                tool_executor=executor,
                max_tokens=max_tokens,
            )
