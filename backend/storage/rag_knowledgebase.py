"""
活动案例 RAG 知识库（CaseStore）

三层协调（Milvus 用原生 pymilvus，embedding 用 LangChain）：
- Milvus：向量检索（HNSW + COSINE），召回 case_id
- MySQL：案例全文 + 结构化 metadata（CasesDB）
- Redis：embedding 向量缓存 + 热案例缓存（RedisCache）

检索策略：向量相似 + 同城市 + 人数区间过滤（混合检索）
入库策略：MySQL 全文 → Milvus 向量 → Redis 热案例

任一组件不可用时优雅降级（返回空），主流程走兜底。
"""
import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional, Dict, Any, List, Tuple

try:
    from pymilvus import MilvusClient, CollectionSchema, FieldSchema, DataType
    try:
        from pymilvus.milvus_client.index import IndexParams as MilvusIndexParams
    except ImportError:  # pragma: no cover
        MilvusIndexParams = None
    PYMILVUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    MilvusIndexParams = None
    PYMILVUS_AVAILABLE = False

from ..core.config import Config
from .database import CasesDB
from .cache import RedisCache
from .embedder import EmbeddingService

logger = logging.getLogger(__name__)


class CaseStore:
    """活动案例知识库（单例）"""

    _milvus_client = None
    _milvus_available: Optional[bool] = None
    # 与 CasesDB 相同：失败后冷却再探测，基础设施恢复后自动重连
    _milvus_next_probe_at: float = 0.0
    _PROBE_COOLDOWN = 30.0

    # ---------- 工具方法 ----------

    @staticmethod
    async def _run_sync(fn, *args, **kwargs):
        """把同步阻塞调用丢进线程池，避免阻塞事件循环"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # ---------- Milvus 连接（原生 pymilvus）----------

    @classmethod
    async def _get_milvus(cls):
        if not PYMILVUS_AVAILABLE or not Config.ENABLE_RAG:
            return None
        if cls._milvus_available is False and time.monotonic() < cls._milvus_next_probe_at:
            return None
        if cls._milvus_client is not None:
            return cls._milvus_client

        try:
            client = MilvusClient(uri=Config.MILVUS_URI)
            await cls._run_sync(client.list_collections)
            await cls._ensure_collection(client)
            cls._milvus_client = client
            cls._milvus_available = True
            logger.info(f"Milvus 已连接: {Config.MILVUS_URI}")
            return client
        except Exception as e:
            cls._milvus_available = False
            cls._milvus_next_probe_at = time.monotonic() + cls._PROBE_COOLDOWN
            logger.warning(f"Milvus 不可用，向量检索降级关闭（{cls._PROBE_COOLDOWN:.0f}s 后重试）: {e}")
            return None

    @classmethod
    def _build_index_params(cls):
        """构造 embedding 字段的 HNSW 索引参数"""
        if MilvusIndexParams is not None:
            index_params = MilvusIndexParams()
            index_params.add_index(
                field_name="embedding",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 256},
            )
            return index_params
        return {
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 256},
        }

    @classmethod
    async def _ensure_collection(cls, client):
        """确保 collection 存在（自动建表 + 索引 + 加载）"""
        col = Config.MILVUS_COLLECTION

        # 1. 建集合（schema 方式，索引单独建）
        if not await cls._run_sync(client.has_collection, col):
            schema = CollectionSchema(
                fields=[
                    FieldSchema("case_id", DataType.VARCHAR, is_primary=True, max_length=64),
                    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=Config.KB_EMBEDDING_DIM),
                    FieldSchema("activity_type", DataType.VARCHAR, max_length=32),
                    FieldSchema("city", DataType.VARCHAR, max_length=64),
                    FieldSchema("attendee_count", DataType.INT64),
                ],
                description="活动策划成功案例",
            )
            await cls._run_sync(client.create_collection, col, schema=schema)
            logger.info(f"Milvus collection 已创建: {col}")

        # 2. 确保索引存在（无索引时搜索/加载会失败）
        try:
            indexes = await cls._run_sync(client.list_indexes, col)
            if not indexes:
                await cls._run_sync(client.create_index, col, cls._build_index_params())
                logger.info(f"Milvus 索引已创建: {col}")
        except Exception as e:
            logger.warning(f"Milvus 索引检查/创建异常: {e}")

        # 3. 加载集合到内存（search/query 前提）
        try:
            await cls._run_sync(client.load_collection, col)
        except Exception as e:
            logger.warning(f"Milvus 集合加载失败: {e}")

    # ---------- 检索文本构造 ----------

    @staticmethod
    def build_embed_text(metadata: Dict[str, Any], plan_text: str = "") -> str:
        """构造用于 embedding 的检索文本。

        以结构化字段为主（活动类型/人数/城市/预算/主题最能区分案例），
        方案正文只取很短摘要，避免同类方案的长文本结构淹没区分信号。
        """
        parts = []
        if metadata.get("activity_type"):
            parts.append(metadata["activity_type"])
        if metadata.get("attendee_count"):
            parts.append(f"{metadata['attendee_count']}人")
        if metadata.get("city"):
            parts.append(metadata["city"])
        if metadata.get("budget"):
            parts.append(f"预算{metadata['budget']}元")
        if metadata.get("theme"):
            parts.append(metadata["theme"])
        if plan_text:
            # 只取第一句概要，避免长方案正文稀释结构化字段
            first_sentence = plan_text.strip().split("\n")[0][:80]
            parts.append(first_sentence)
        return " ".join(parts)

    @staticmethod
    def _build_filter(city: Optional[str], attendee_count: Optional[int]) -> Optional[str]:
        """构造 Milvus 过滤表达式：同城市 + 人数区间"""
        parts = []
        if city:
            parts.append(f'city == "{city}"')
        if attendee_count:
            rng = Config.KB_ATTENDEE_RANGE
            lo = max(0, attendee_count - rng)
            hi = attendee_count + rng
            parts.append(f"attendee_count >= {lo} and attendee_count <= {hi}")
        return " and ".join(parts) if parts else None

    # ---------- 入库 ----------

    @classmethod
    async def add_case(
        cls,
        plan_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        embed_text: Optional[str] = None,
    ) -> Optional[str]:
        """保存一条案例。成功返回 case_id，否则返回 None（校验失败拒绝入库）"""
        from ..core.models import Case
        from pydantic import ValidationError

        metadata = metadata or {}

        # 企业级：pydantic 校验案例数据，非法数据直接拒绝
        try:
            case = Case(plan_text=plan_text, **metadata)
        except ValidationError as e:
            logger.warning(f"案例校验失败，拒绝入库: {e.errors()}")
            return None

        case_id = case.id
        embed_text = embed_text or cls.build_embed_text(metadata, case.plan_text)

        # 1. embedding
        vec = await EmbeddingService.embed(embed_text)

        # 2. MySQL 全文
        case_row = {
            "id": case_id,
            "activity_type": case.activity_type,
            "attendee_count": case.attendee_count,
            "budget": case.budget,
            "city": case.city,
            "theme": case.theme,
            "plan_text": case.plan_text,
            "embed_text": embed_text,
            "source": case.source,
            "status": case.status,
        }
        db_ok = await CasesDB.insert_case(case_row)

        # 3. Milvus 向量
        vec_ok = False
        if vec:
            client = await cls._get_milvus()
            if client is not None:
                try:
                    await cls._run_sync(
                        client.insert,
                        Config.MILVUS_COLLECTION,
                        [{
                            "case_id": case_id,
                            "embedding": vec,
                            "activity_type": case.activity_type or "",
                            "city": case.city or "",
                            "attendee_count": case.attendee_count or 0,
                        }],
                    )
                    # 强制落盘，确保插入后立即可检索
                    try:
                        await cls._run_sync(client.flush, Config.MILVUS_COLLECTION)
                    except Exception as fe:
                        logger.debug(f"Milvus flush 跳过: {fe}")
                    vec_ok = True
                except Exception as e:
                    logger.warning(f"Milvus 写入失败: {e}")

        # 4. Redis 热案例
        await RedisCache.set_case(case_id, case_row)

        if db_ok or vec_ok:
            logger.info(f"案例入库成功: {case_id}（db={db_ok}, vec={vec_ok}）")
            return case_id
        logger.warning(f"案例入库失败（DB 和 Milvus 均不可用）: {case_id}")
        return None

    # ---------- 检索 ----------

    @classmethod
    async def search_cases(
        cls,
        query_text: str,
        top_k: Optional[int] = None,
        city: Optional[str] = None,
        attendee_count: Optional[int] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """混合检索：向量相似 + 同城市 + 人数区间。

        Returns: [(case_dict, score), ...]，按相似度降序
        """
        top_k = top_k or Config.KB_TOP_K

        # 1. 查询向量
        vec = await EmbeddingService.embed(query_text)
        if not vec:
            return []

        # 2. Milvus 检索
        client = await cls._get_milvus()
        if client is None:
            return []
        try:
            expr = cls._build_filter(city, attendee_count)
            hits = await cls._run_sync(
                client.search,
                Config.MILVUS_COLLECTION,
                data=[vec],
                limit=top_k * 3,          # 多召回再按阈值筛
                filter=expr,
                output_fields=["case_id"],
            )
        except Exception as e:
            logger.warning(f"Milvus 检索失败: {e}")
            return []

        if not hits or not hits[0]:
            return []

        # 3. 阈值过滤 + 按分数排序
        scored = {}
        for h in hits[0]:
            score = float(h.get("distance", 0))
            if score < Config.KB_SIMILARITY_THRESHOLD:
                continue
            scored[h["id"]] = score
        if not scored:
            return []

        ordered_ids = sorted(scored, key=lambda cid: scored[cid], reverse=True)[:top_k]

        # 4. 取全文：Redis 命中 → 否则查 MySQL
        case_map: Dict[str, Dict[str, Any]] = {}
        for cid in ordered_ids:
            c = await RedisCache.get_case(cid)
            if c:
                case_map[cid] = c

        missed = [cid for cid in ordered_ids if cid not in case_map]
        if missed:
            for c in await CasesDB.get_cases_by_ids(missed):
                case_map[c["id"]] = c
                await RedisCache.set_case(c["id"], c)

        result = []
        for cid in ordered_ids:
            case = case_map.get(cid)
            if case:
                result.append((case, scored[cid]))
        return result

    # ---------- 管理 ----------

    @classmethod
    async def list_cases(cls, limit: int = 100) -> List[Dict[str, Any]]:
        return await CasesDB.list_cases(limit)

    @classmethod
    async def delete_case(cls, case_id: str) -> bool:
        ok = await CasesDB.delete_case(case_id)
        client = await cls._get_milvus()
        if client is not None:
            try:
                await cls._run_sync(
                    client.delete,
                    Config.MILVUS_COLLECTION,
                    filter=f'case_id == "{case_id}"',
                )
            except Exception as e:
                logger.warning(f"Milvus 删除失败: {e}")
        await RedisCache.delete_case(case_id)
        return ok

    # ---------- 批量导入 ----------

    @classmethod
    async def import_from_file(cls, path: str) -> Dict[str, Any]:
        """从文件批量导入案例。

        - .json：数组或 {cases: [...]}，每项 {plan_text, metadata}
        - .txt/.md：整个文件作为一条案例（metadata 为空）
        Returns: {imported, failed, ids}
        """
        if not os.path.exists(path):
            return {"imported": 0, "failed": 0, "ids": [], "error": "文件不存在"}

        imported, failed, ids = 0, 0, []
        ext = os.path.splitext(path)[1].lower()

        try:
            if ext == ".json":
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("cases", data) if isinstance(data, dict) else data
                for item in items:
                    plan = item.get("plan_text") or item.get("plan") or ""
                    meta = item.get("metadata") or {}
                    cid = await cls.add_case(plan, meta)
                    if cid:
                        imported += 1
                        ids.append(cid)
                    else:
                        failed += 1
            else:
                with open(path, "r", encoding="utf-8") as f:
                    plan = f.read()
                cid = await cls.add_case(plan, {})
                if cid:
                    imported, ids = 1, [cid]
                else:
                    failed = 1
        except Exception as e:
            logger.error(f"导入失败: {e}")
            return {"imported": imported, "failed": failed + 1, "ids": ids, "error": str(e)}

        logger.info(f"批量导入完成: 成功 {imported}, 失败 {failed}")
        return {"imported": imported, "failed": failed, "ids": ids}
