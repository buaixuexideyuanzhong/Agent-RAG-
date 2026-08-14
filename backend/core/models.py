"""
Pydantic 数据校验模型（企业级）

统一管理系统内流动的关键数据：
- Requirements   需求提取结果（LLM 输出 → 结构化）
- Case           案例入库（RAG 知识库）
- UserRequest    用户输入

校验失败会被拒/降级，非法数据不进入系统核心流程。
"""
import uuid
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


def _coerce_number(value):
    """把 LLM 常见的字符串数字转为数值（支持 '20万'/'500' 等）"""
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            raise ValueError("空数字")
        # 中文/英文单位 '万' / 'w'
        for unit, mult in (("万", 10000.0), ("w", 10000.0), ("W", 10000.0), ("亿", 1e8)):
            if s.endswith(unit):
                try:
                    return float(s[: -len(unit)]) * mult
                except ValueError:
                    raise ValueError(f"无法解析数字: {value!r}")
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"无法解析数字: {value!r}")
    raise ValueError(f"无法解析数字: {value!r}")


class Requirements(BaseModel):
    """需求提取结果：LLM 从自然语言提取的结构化活动需求"""

    model_config = ConfigDict(extra="ignore")

    activity_type: Optional[str] = Field(None, max_length=32, description="活动类型（年会/发布会/培训会等）")
    theme: Optional[str] = Field(None, max_length=256, description="活动主题")
    attendee_count: Optional[int] = Field(None, gt=0, le=100_000, description="参与人数")
    budget: Optional[float] = Field(None, ge=0, le=1_000_000_000, description="预算（元）")
    city: Optional[str] = Field(None, max_length=64, description="城市")
    preferred_area: Optional[str] = Field(None, max_length=64, description="偏好区域")
    time: Optional[str] = Field(None, max_length=64, description="活动时间")
    duration: Optional[str] = Field(None, max_length=64, description="活动时长")
    special_requirements: Optional[List[str]] = Field(None, max_length=50, description="特殊需求列表")

    @field_validator("attendee_count", "budget", mode="before")
    @classmethod
    def _coerce_numeric(cls, value):
        return _coerce_number(value)

    @field_validator("activity_type", "city", "theme", mode="before")
    @classmethod
    def _clean_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("special_requirements", mode="before")
    @classmethod
    def _clean_list(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            # LLM 可能返回逗号分隔字符串
            return [s.strip() for s in value.split(",") if s.strip()]
        if isinstance(value, list):
            return [str(s).strip() for s in value if str(s).strip()]
        return None


class Case(BaseModel):
    """活动案例：RAG 知识库入库记录"""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    activity_type: Optional[str] = Field(None, max_length=32)
    attendee_count: Optional[int] = Field(None, gt=0, le=100_000)
    budget: Optional[float] = Field(None, ge=0, le=1_000_000_000)
    city: Optional[str] = Field(None, max_length=64)
    theme: Optional[str] = Field(None, max_length=256)
    plan_text: str = Field(min_length=1, max_length=50_000, description="完整策划方案")
    embed_text: Optional[str] = Field(None, max_length=10_000)
    source: str = Field(default="user_confirmed", pattern="^(user_confirmed|imported)$")
    status: str = Field(default="active", pattern="^(active|archived)$")

    @field_validator("attendee_count", "budget", mode="before")
    @classmethod
    def _coerce_numeric(cls, value):
        return _coerce_number(value)

    @field_validator("plan_text", mode="before")
    @classmethod
    def _clean_plan(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class UserRequest(BaseModel):
    """用户输入校验"""

    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, max_length=2000, description="用户需求描述")

    @field_validator("text", mode="before")
    @classmethod
    def _clean_text(cls, value):
        if value is None:
            raise ValueError("输入不能为空")
        if isinstance(value, str):
            s = value.strip()
            if not s:
                raise ValueError("输入不能为空")
            return s
        return value
