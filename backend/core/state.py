"""
智能体状态定义
使用 TypedDict 定义各 Agent 共享的状态
"""
from typing import TypedDict, Optional, Dict, Any, List
from typing_extensions import Annotated
import operator
import asyncio


class AgentState(TypedDict):
    """
    多智能体系统的共享状态

    字段说明:
    - user_request: 用户原始的自然语言输入
    - extracted_requirements: 提取出的结构化需求
    - venue_result: 场地搜索结果
    - supplier_result: 商家搜索结果
    - process_result: 流程参考搜索结果
    - final_plan: 最终生成的活动策划方案
    - plan_streamed: 方案是否已通过流式输出实时打印（避免重复展示）
    - messages: 消息历史，用于 LangChain 的消息传递
    - errors: 错误信息收集
    - stream_queue: （API SSE 专用）方案文本 chunk 队列，None 表示非流式
    - console_output: （API 专用）是否打印到控制台，None 回退到 Config.ENABLE_STREAM_OUTPUT
    """
    user_request: str
    extracted_requirements: Optional[Dict[str, Any]]
    venue_result: Optional[str]
    supplier_result: Optional[str]
    process_result: Optional[str]
    final_plan: Optional[str]
    plan_streamed: bool
    messages: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]
    # 后端 API SSE 流式输出专用（CLI 不传，走默认回退）
    stream_queue: Optional[asyncio.Queue]   # 方案文本 chunk 队列（("chunk", delta) / ("done", None)）
    console_output: Optional[bool]          # 是否打印到控制台；None 回退到 Config.ENABLE_STREAM_OUTPUT


class RequirementExtracted(TypedDict):
    """提取出的活动需求结构"""
    activity_type: str  # 活动类型：年会、发布会、培训会等
    theme: Optional[str]  # 活动主题
    attendee_count: int  # 参与人数
    budget: float  # 预算（元）
    city: str  # 城市
    preferred_area: Optional[str]  # 偏好区域
    time: Optional[str]  # 活动时间
    duration: Optional[str]  # 活动时长
    special_requirements: Optional[List[str]]  # 特殊需求列表