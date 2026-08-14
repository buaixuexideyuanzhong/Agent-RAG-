"""
Redis 缓存层

缓存对象：
- LLM 响应（llm:）   相同 prompt 复用，省 token、抗 429
- 工具结果（tool:）  相同高德/百度/博查查询复用，省额度
- Embedding（emb:）  相同文本不重复调 embedding API
- 热案例（case:）    检索命中后整条缓存

设计要点：Redis 不可用时所有操作降级为 no-op，不影响主流程。
首次连接失败后标记不可用，后续不再重试，避免每次调用都卡超时。
"""
import hashlib
import json
import logging
from typing import Optional, Any, List, Dict

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    REDIS_AVAILABLE = False

from ..core.config import Config

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis 缓存封装（单例 + 优雅降级）"""

    _client = None
    # None=未探测, True=可用, False=不可用
    _available: Optional[bool] = None

    # ---------- 连接管理 ----------

    @classmethod
    async def _get_client(cls):
        """获取 Redis 客户端，不可用返回 None"""
        if not REDIS_AVAILABLE or not Config.REDIS_ENABLED:
            return None
        if cls._available is False:
            return None
        if cls._client is not None and cls._available is True:
            return cls._client

        # 首次连接
        try:
            cls._client = aioredis.from_url(
                Config.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await cls._client.ping()
            cls._available = True
            logger.info(f"Redis 已连接: {Config.REDIS_URL}")
            return cls._client
        except Exception as e:
            cls._available = False
            cls._client = None
            logger.warning(f"Redis 不可用，缓存降级关闭: {e}")
            return None

    @classmethod
    async def close(cls):
        """关闭连接（进程退出时调用）"""
        if cls._client is not None:
            try:
                await cls._client.close()
            except Exception:
                pass
            cls._client = None

    # ---------- 通用 get/set/delete ----------

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        client = await cls._get_client()
        if client is None:
            return None
        try:
            return await client.get(key)
        except Exception as e:
            logger.debug(f"Redis get 失败({key}): {e}")
            return None

    @classmethod
    async def set(cls, key: str, value: str, ttl: Optional[int] = None) -> bool:
        client = await cls._get_client()
        if client is None:
            return False
        try:
            if ttl and ttl > 0:
                await client.set(key, value, ex=ttl)
            else:
                await client.set(key, value)
            return True
        except Exception as e:
            logger.debug(f"Redis set 失败({key}): {e}")
            return False

    @classmethod
    async def delete(cls, key: str) -> bool:
        client = await cls._get_client()
        if client is None:
            return False
        try:
            await client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Redis delete 失败({key}): {e}")
            return False

    # ---------- 工具方法 ----------

    @staticmethod
    def hash_key(*parts: Any) -> str:
        """根据各部分生成稳定的 md5 键"""
        raw = "|".join(str(p) for p in parts)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    # ---------- 业务封装：LLM 响应 ----------

    @classmethod
    async def get_llm(cls, model: str, system_prompt: str, user_message: str) -> Optional[str]:
        if not Config.ENABLE_LLM_CACHE:
            return None
        key = "llm:" + cls.hash_key(model, system_prompt, user_message)
        return await cls.get(key)

    @classmethod
    async def set_llm(cls, model: str, system_prompt: str, user_message: str, value: str) -> bool:
        if not Config.ENABLE_LLM_CACHE:
            return False
        key = "llm:" + cls.hash_key(model, system_prompt, user_message)
        return await cls.set(key, value, ttl=Config.LLM_CACHE_TTL)

    # ---------- 业务封装：工具结果 ----------

    @classmethod
    async def get_tool(cls, name: str, args: Dict[str, Any]) -> Optional[str]:
        if not Config.ENABLE_TOOL_CACHE:
            return None
        key = "tool:" + cls.hash_key(name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        return await cls.get(key)

    @classmethod
    async def set_tool(cls, name: str, args: Dict[str, Any], value: str) -> bool:
        if not Config.ENABLE_TOOL_CACHE:
            return False
        key = "tool:" + cls.hash_key(name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        return await cls.set(key, value, ttl=Config.TOOL_CACHE_TTL)

    # ---------- 业务封装：Embedding 向量 ----------

    @classmethod
    async def get_embedding(cls, text: str) -> Optional[List[float]]:
        key = "emb:" + cls.hash_key(text)
        v = await cls.get(key)
        if v is None:
            return None
        try:
            return json.loads(v)
        except Exception:
            return None

    @classmethod
    async def set_embedding(cls, text: str, vector: List[float]) -> bool:
        key = "emb:" + cls.hash_key(text)
        # embedding 不设 TTL（文本→向量是确定性的）
        return await cls.set(key, json.dumps(vector))

    # ---------- 业务封装：热案例 ----------

    @classmethod
    async def get_case(cls, case_id: str) -> Optional[Dict[str, Any]]:
        key = "case:" + case_id
        v = await cls.get(key)
        if v is None:
            return None
        try:
            return json.loads(v)
        except Exception:
            return None

    @classmethod
    async def set_case(cls, case_id: str, case: Dict[str, Any]) -> bool:
        key = "case:" + case_id
        return await cls.set(key, json.dumps(case, ensure_ascii=False), ttl=Config.CASE_CACHE_TTL)

    @classmethod
    async def delete_case(cls, case_id: str) -> bool:
        return await cls.delete("case:" + case_id)
