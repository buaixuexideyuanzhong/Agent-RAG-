"""
MySQL 结构化存储层：活动案例全量数据

职责：案例全文 + 结构化 metadata 的持久化与查询。
Milvus 只存向量+id，全文都在这里。

设计要点：MySQL 不可用时（如 Docker 未启动）所有操作降级，
返回 None / 空列表，不抛异常，主流程不受影响
（process 节点 RAG 无命中 → 自动走博查/LLM 兜底）。
"""
import logging
import time
from typing import Optional, Dict, Any, List

try:
    import aiomysql
    MYSQL_AVAILABLE = True
except ImportError:  # pragma: no cover
    MYSQL_AVAILABLE = False

from ..core.config import Config

logger = logging.getLogger(__name__)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS activity_cases (
    id              VARCHAR(64) PRIMARY KEY,
    activity_type   VARCHAR(32),
    attendee_count  INT,
    budget          DECIMAL(12,2),
    city            VARCHAR(64),
    theme           VARCHAR(256),
    plan_text       MEDIUMTEXT,
    embed_text      TEXT,
    source          VARCHAR(32),
    status          VARCHAR(16) DEFAULT 'active',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_type   (activity_type),
    INDEX idx_city   (city),
    INDEX idx_count  (attendee_count)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""


class CasesDB:
    """活动案例 MySQL 存储（连接池单例 + 优雅降级）"""

    _pool = None
    # None=未探测, True=可用, False=不可用
    _available: Optional[bool] = None
    # 探测失败后的冷却期（秒）。避免每次调用都等 connect_timeout=5s；
    # 冷却结束自动重新探测，基础设施恢复后无需重启进程即可重连。
    _next_probe_at: float = 0.0
    _PROBE_COOLDOWN = 30.0

    # ---------- 连接管理 ----------

    @classmethod
    async def _get_pool(cls):
        if not MYSQL_AVAILABLE or not Config.DB_ENABLED:
            return None
        if cls._available is False and time.monotonic() < cls._next_probe_at:
            return None
        if cls._pool is not None and cls._available is True:
            return cls._pool

        try:
            cls._pool = await aiomysql.create_pool(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                db=Config.DB_NAME,
                autocommit=True,
                minsize=1,
                maxsize=5,
                connect_timeout=5,
                charset="utf8mb4",
            )
            # 探活 + 建库建表
            async with cls._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.execute(CREATE_TABLE_SQL)
            cls._available = True
            logger.info(f"MySQL 已连接: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
            return cls._pool
        except Exception as e:
            cls._available = False
            cls._next_probe_at = time.monotonic() + cls._PROBE_COOLDOWN
            if cls._pool is not None:
                cls._pool.close()
                cls._pool = None
            logger.warning(f"MySQL 不可用，案例库降级关闭（{cls._PROBE_COOLDOWN:.0f}s 后重试）: {e}")
            return None

    @classmethod
    async def close(cls):
        if cls._pool is not None:
            try:
                cls._pool.close()
                await cls._pool.wait_closed()
            except Exception:
                pass
            cls._pool = None
        cls._available = None

    @staticmethod
    def _row_to_case(row) -> Dict[str, Any]:
        return {
            "id": row[0],
            "activity_type": row[1],
            "attendee_count": row[2],
            "budget": float(row[3]) if row[3] is not None else None,
            "city": row[4],
            "theme": row[5],
            "plan_text": row[6],
            "embed_text": row[7],
            "source": row[8],
            "status": row[9],
            "created_at": str(row[10]) if row[10] else None,
        }

    # ---------- CRUD ----------

    @classmethod
    async def insert_case(cls, case: Dict[str, Any]) -> Optional[str]:
        """插入案例，返回 case_id；DB 不可用返回 None"""
        pool = await cls._get_pool()
        if pool is None:
            return None
        sql = (
            "INSERT INTO activity_cases "
            "(id, activity_type, attendee_count, budget, city, theme, "
            " plan_text, embed_text, source, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        params = (
            case["id"],
            case.get("activity_type"),
            case.get("attendee_count"),
            case.get("budget"),
            case.get("city"),
            case.get("theme"),
            case.get("plan_text"),
            case.get("embed_text"),
            case.get("source", "user_confirmed"),
            case.get("status", "active"),
        )
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
            return case["id"]
        except Exception as e:
            logger.error(f"插入案例失败: {e}")
            return None

    @classmethod
    async def get_case(cls, case_id: str) -> Optional[Dict[str, Any]]:
        pool = await cls._get_pool()
        if pool is None:
            return None
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT * FROM activity_cases WHERE id=%s", (case_id,)
                    )
                    row = await cur.fetchone()
                    return cls._row_to_case(row) if row else None
        except Exception as e:
            logger.error(f"查询案例失败: {e}")
            return None

    @classmethod
    async def get_cases_by_ids(cls, case_ids: List[str]) -> List[Dict[str, Any]]:
        """批量按 id 取案例（向量检索后取全文用）"""
        pool = await cls._get_pool()
        if pool is None or not case_ids:
            return []
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    placeholders = ",".join(["%s"] * len(case_ids))
                    await cur.execute(
                        f"SELECT * FROM activity_cases "
                        f"WHERE id IN ({placeholders}) AND status='active'",
                        tuple(case_ids),
                    )
                    rows = await cur.fetchall()
                    return [cls._row_to_case(r) for r in rows]
        except Exception as e:
            logger.error(f"批量查询案例失败: {e}")
            return []

    @classmethod
    async def list_cases(cls, limit: int = 100) -> List[Dict[str, Any]]:
        pool = await cls._get_pool()
        if pool is None:
            return []
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT * FROM activity_cases WHERE status='active' "
                        "ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                    rows = await cur.fetchall()
                    return [cls._row_to_case(r) for r in rows]
        except Exception as e:
            logger.error(f"列出案例失败: {e}")
            return []

    @classmethod
    async def delete_case(cls, case_id: str) -> bool:
        pool = await cls._get_pool()
        if pool is None:
            return False
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM activity_cases WHERE id=%s", (case_id,)
                    )
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"删除案例失败: {e}")
            return False
