"""
Pydantic Schema：请求/响应模型
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime


# ─── 用户 ───

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool = False
    is_active: bool = True
    created_at: datetime
    # LLM 配置随登录响应一起返回（前端直接读取，无需再请求）
    llm_api_key:  Optional[str] = None
    llm_base_url: Optional[str] = "https://gpt-agent.cc/v1"
    llm_model:    Optional[str] = "deepseek-v4-flash"

    model_config = {"from_attributes": True}


class UserConfigUpdate(BaseModel):
    """更新用户 LLM 配置"""
    llm_api_key:  Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model:    Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LLMTestRequest(BaseModel):
    api_key:  str
    base_url: str = "https://gpt-agent.cc/v1"
    model:    str = "deepseek-v4-flash"


# ─── 任务 ───

class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    llm_api_key: str = Field(..., min_length=10)
    llm_base_url: str = Field(default="https://gpt-agent.cc/v1")
    llm_model: str = Field(default="deepseek-v4-flash")
    # 指令列表：[{"id": 1, "instruction": "..."}]
    instructions: List[dict] = Field(default_factory=list)

class TaskOut(BaseModel):
    id: str
    name: str
    status: str
    progress: int
    total_sessions: int
    done_sessions: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_msg: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── 会话结果 ───

class SessionOut(BaseModel):
    id: str
    session_id: str
    instruction_id: Optional[int] = None
    persona: Optional[str] = None
    total_turns: int
    agent_turns: int
    final_score: float
    grade: str
    review_flag: bool
    review_reason: Optional[str] = None
    review_status: Optional[str] = "pending"
    review_comment: Optional[str] = None
    review_by: Optional[str] = None
    result_json: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── 人工审核提交 ───

class ReviewSubmit(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|override)$")  # 通过/驳回/改分
    comment: Optional[str] = None
    score_overrides: Optional[dict] = None  # {dim: new_score} 改分专用


# ─── 汇总统计 ───

class AggregateReport(BaseModel):
    total_sessions: int
    review_count: int
    overall_avg_score: float
    overall_max_score: float
    overall_min_score: float
    grade_distribution: dict
    by_persona: dict
    dimension_avg: dict
