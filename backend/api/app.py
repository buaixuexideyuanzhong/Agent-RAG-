"""
活动策划多智能体系统 - FastAPI 后端

前后端分离后的后端服务，以 HTTP API 暴露系统的全部能力：
- 策划接口：普通 JSON（POST /api/v1/plan）+ SSE 流式（POST /api/v1/plan/stream）
- 案例知识库：保存 / 列表 / 删除 / 文件导入
- 健康检查 / 工作流信息

启动（需在项目根目录）：
    uvicorn backend.api.app:app --reload --port 8000

文档：启动后访问 http://127.0.0.1:8000/docs（Swagger UI）
"""
import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ..core.config import Config
from ..agents.workflow import WORKFLOW_STRUCTURE
from ..cli.main import ActivityPlanner
from ..storage.rag_knowledgebase import CaseStore

# 配置日志
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== Pydantic 请求模型 ====================

class PlanRequest(BaseModel):
    """策划请求体（去空格后拒绝空串，与 models.UserRequest 一致）"""
    request: str = Field(..., max_length=2000, description="用户的自然语言需求描述")

    @field_validator("request", mode="before")
    @classmethod
    def _clean_text(cls, value):
        if value is None:
            raise ValueError("request 不能为空")
        if isinstance(value, str):
            s = value.strip()
            if not s:
                raise ValueError("request 不能为空")
            return s
        return value


class CaseCreate(BaseModel):
    """保存案例请求体"""
    plan_text: str = Field(..., min_length=1, max_length=50_000, description="完整策划方案")
    metadata: Optional[dict] = None


# ==================== Pydantic 响应模型（HTTP 契约，前端据此生成类型）====================

class HealthModels(BaseModel):
    planner: str
    searcher: str


class HealthTools(BaseModel):
    amap: bool
    baidu: bool
    bocha: bool


class HealthInfra(BaseModel):
    redis_enabled: bool
    db_enabled: bool
    rag_enabled: bool


class HealthResponse(BaseModel):
    """GET /api/v1/health 响应"""
    status: str
    api_key_set: bool
    models: HealthModels
    tools: HealthTools
    infra: HealthInfra


class WorkflowResponse(BaseModel):
    """GET /api/v1/workflow 响应"""
    structure: str
    info: str


class PlanResponse(BaseModel):
    """POST /api/v1/plan 响应（成功/失败共用；未提供的字段取默认值）"""
    success: bool
    plan: Optional[str] = None
    plan_streamed: bool = False
    requirements: Optional[Dict[str, Any]] = None
    venue_info: Optional[str] = None
    supplier_info: Optional[str] = None
    process_info: Optional[str] = None
    messages: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class CaseOut(BaseModel):
    """案例列表中的单条记录（内部 embed_text 不对外暴露）"""
    id: str
    activity_type: Optional[str] = None
    attendee_count: Optional[int] = None
    budget: Optional[float] = None
    city: Optional[str] = None
    theme: Optional[str] = None
    plan_text: str
    source: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


class CaseListResponse(BaseModel):
    """GET /api/v1/cases 响应"""
    cases: List[CaseOut]


class CaseCreateResponse(BaseModel):
    """POST /api/v1/cases 响应"""
    case_id: str


class CaseDeleteResponse(BaseModel):
    """DELETE /api/v1/cases/{case_id} 响应"""
    deleted: bool


class ImportResponse(BaseModel):
    """POST /api/v1/cases/import 响应"""
    imported: int
    failed: int
    ids: List[str]
    error: Optional[str] = None


# ==================== Planner 单例 ====================

_planner: Optional[ActivityPlanner] = None


def get_planner() -> ActivityPlanner:
    """懒加载全局 Planner 单例（跨请求复用；workflow 无 checkpointer，可并发重入）"""
    global _planner
    if _planner is None:
        _planner = ActivityPlanner()
        logger.info("全局 ActivityPlanner 已初始化")
    return _planner


# ==================== 应用与生命周期 ====================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动时预热工作流；关闭时释放连接池"""
    # 注意：不调用 Config.validate()——它会 print emoji，非 TTY/GBK 环境下可能崩溃；
    # 配置状态由 /api/v1/health 端点对外报告。
    if not Config.LLM_API_KEY:
        logger.warning("LLM_API_KEY 未设置，策划接口将不可用")
    else:
        get_planner()  # 预热：构建工作流图
    yield
    from ..storage.cache import RedisCache
    from ..storage.database import CasesDB
    await RedisCache.close()
    await CasesDB.close()
    logger.info("连接池已关闭")


app = FastAPI(
    title="活动策划多智能体系统 API",
    description="基于 LangGraph + 智谱 AI GLM 的多智能体活动策划后端",
    version="1.0.0",
    lifespan=lifespan,
)

# 开发期 CORS 全放行（前端后续跨域访问用；生产环境应收紧为白名单）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 工具函数 ====================

def _sse(payload: dict) -> str:
    """把字典序列化为 SSE 事件帧"""
    import json
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ==================== 路由（版本化：/api/v1，未来 v2 平行新增不破坏 v1）====================

v1 = APIRouter(prefix="/api/v1", tags=["v1"])


# ==================== 健康检查 / 工作流信息 ====================

@v1.get("/health", response_model=HealthResponse)
async def health():
    """服务健康状态：配置完整性 + 工具 key + 基础设施开关"""
    return {
        "status": "ok" if Config.LLM_API_KEY else "degraded",
        "api_key_set": bool(Config.LLM_API_KEY),
        "models": {
            "planner": Config.PLANNER_MODEL,
            "searcher": Config.SEARCHER_MODEL,
        },
        "tools": {
            "amap": bool(Config.AMAP_API_KEY),
            "baidu": bool(Config.BAIDU_MAP_AK),
            "bocha": bool(Config.BOCHA_API_KEY),
        },
        "infra": {
            "redis_enabled": Config.REDIS_ENABLED,
            "db_enabled": Config.DB_ENABLED,
            "rag_enabled": Config.ENABLE_RAG,
        },
    }


@v1.get("/workflow", response_model=WorkflowResponse)
async def workflow_info():
    """工作流结构说明"""
    return {
        "structure": WORKFLOW_STRUCTURE,
        "info": get_planner().get_workflow_info(),
    }


# ==================== 策划接口 ====================

@v1.post("/plan", response_model=PlanResponse)
async def plan(req: PlanRequest):
    """单次策划：阻塞到完整方案生成后一次性返回 JSON"""
    result = await get_planner().plan(req.request, console_output=False)
    # 从返回结果中移除 SSE 专用字段，保持对外 JSON 纯净
    result.pop("stream_queue", None)
    return result


@v1.post("/plan/stream")
async def plan_stream(req: PlanRequest):
    """SSE 流式策划：方案文本实时以 chunk 推送，结束时返回完整 result

    事件格式（text/event-stream）：
        data: {"type":"chunk","delta":"..."}\n\n
        data: {"type":"done","result":{...}}\n\n
    """
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        get_planner().plan(req.request, stream_queue=queue, console_output=False)
    )

    async def event_gen() -> AsyncIterator[str]:
        try:
            while True:
                if task.done():
                    # 工作流已完成：产出最终 result 并结束
                    result = task.result()
                    result.pop("stream_queue", None)
                    yield _sse({"type": "done", "result": result})
                    return
                try:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                if kind == "chunk":
                    yield _sse({"type": "chunk", "delta": payload})
                elif kind == "error":
                    if not task.done():
                        task.cancel()
                    yield _sse({"type": "error", "error": str(payload)})
                    return
                # "done" 哨兵：交给 task.done() 分支统一收尾
        except asyncio.CancelledError:
            # 客户端断开
            if not task.done():
                task.cancel()
            raise
        except Exception as e:
            logger.error(f"SSE 流式策划异常: {e}")
            if not task.done():
                task.cancel()
            yield _sse({"type": "error", "error": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 案例知识库接口 ====================

@v1.get("/cases", response_model=CaseListResponse)
async def list_cases(limit: int = 50):
    """列出知识库案例（按创建时间倒序）"""
    limit = max(1, min(limit, 200))
    return {"cases": await CaseStore.list_cases(limit)}


@v1.post("/cases", response_model=CaseCreateResponse)
async def save_case(case: CaseCreate):
    """把一条案例保存到知识库（成功返回 case_id）"""
    case_id = await CaseStore.add_case(case.plan_text, case.metadata or {})
    if not case_id:
        raise HTTPException(status_code=400, detail="案例保存失败（MySQL/Milvus 不可用，或数据校验失败）")
    return {"case_id": case_id}


@v1.delete("/cases/{case_id}", response_model=CaseDeleteResponse)
async def delete_case(case_id: str):
    """删除知识库中的一条案例"""
    deleted = await CaseStore.delete_case(case_id)
    return {"deleted": deleted}


@v1.post("/cases/import", response_model=ImportResponse)
async def import_cases(file: UploadFile = File(...)):
    """上传文件批量导入案例（支持 .json / .txt / .md）"""
    suffix = Path(file.filename or "cases.json").suffix.lower()
    if suffix not in (".json", ".txt", ".md"):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}（支持 json/txt/md）")

    # 落盘到临时文件，复用 CaseStore.import_from_file 的解析逻辑
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(await file.read())
        tmp.close()
        stats = await CaseStore.import_from_file(tmp.name)
    except Exception as e:
        logger.error(f"案例导入接口失败: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")
    finally:
        if tmp is not None:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except Exception:
                pass

    if stats.get("error"):
        raise HTTPException(status_code=400, detail=stats["error"])
    return stats


# ==================== 挂载路由 ====================

# 当前仅 v1；未来新增 v2 时平行定义 v2_router 并 include，不破坏使用 v1 的前端
app.include_router(v1)


# ==================== 直接运行入口 ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.api.app:app", host="0.0.0.0", port=8000, reload=True)
