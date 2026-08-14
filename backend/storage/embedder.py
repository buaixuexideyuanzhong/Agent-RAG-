"""
Embedding 服务：LangChain HuggingFaceEmbeddings + BGE 中文小模型

- 模型：BAAI/bge-small-zh-v1.5（512 维，本地离线推理，免费）
- 底层用 sentence-transformers；首次从 HuggingFace 下载（可用 HF_ENDPOINT 镜像加速）
- 向量结果写入 Redis 缓存（同文本复用，省重复推理）
- 模型加载失败时优雅降级：embed 返回 None，调用方走兜底
"""
import asyncio
import logging
from typing import Optional, List

try:
    from langchain_huggingface import HuggingFaceEmbeddings
    EMBED_AVAILABLE = True
except ImportError:  # pragma: no cover
    EMBED_AVAILABLE = False

from ..core.config import Config
from .cache import RedisCache

logger = logging.getLogger(__name__)


class EmbeddingService:
    """文本向量化（单例，模型只加载一次）"""

    _embeddings = None
    _available: Optional[bool] = None

    @classmethod
    def _get_embeddings(cls):
        """加载 LangChain HuggingFaceEmbeddings（同步，首次调用时执行）"""
        if cls._available is False:
            return None
        if cls._embeddings is not None:
            return cls._embeddings
        if not EMBED_AVAILABLE:
            logger.warning("langchain-huggingface 未安装，embedding 不可用")
            cls._available = False
            return None
        try:
            logger.info(f"加载本地 embedding 模型 {Config.KB_EMBEDDING_MODEL} ...")
            cls._embeddings = HuggingFaceEmbeddings(
                model_name=Config.KB_EMBEDDING_MODEL,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            cls._available = True
            logger.info("embedding 模型加载完成")
            return cls._embeddings
        except Exception as e:
            cls._available = False
            logger.warning(f"embedding 模型加载失败（可检查网络/镜像）：{e}")
            return None

    @classmethod
    async def embed(cls, text: str) -> Optional[List[float]]:
        """将单条文本向量化，优先走 Redis 缓存"""
        if not text or not text.strip():
            return None

        # 1. Redis 向量缓存
        cached = await RedisCache.get_embedding(text)
        if cached:
            return cached

        # 2. 本地推理（放线程池，避免阻塞事件循环）
        embeddings = cls._get_embeddings()
        if embeddings is None:
            return None

        try:
            vec = await asyncio.get_running_loop().run_in_executor(
                None, lambda: embeddings.embed_query(text)
            )
            vec = list(vec) if vec else []
            if not vec:
                return None
            # 3. 回填缓存
            await RedisCache.set_embedding(text, vec)
            return vec
        except Exception as e:
            logger.warning(f"embedding 推理失败: {e}")
            return None
