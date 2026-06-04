"""
ORM 模型：User / Task / Session / EvaluationResult
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship
from ..database import Base


def _uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# User：用户账号
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id        = Column(String(36), primary_key=True, default=_uuid)
    username  = Column(String(64), unique=True, nullable=False, index=True)
    email     = Column(String(128), unique=True, nullable=False, index=True)
    hashed_pw = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin  = Column(Boolean, default=False)   # 管理员标志
    created_at = Column(DateTime, default=datetime.utcnow)

    # LLM 配置（与账号绑定，跨设备登录自动同步）
    llm_api_key  = Column(String(512), nullable=True)
    llm_base_url = Column(String(256), nullable=True, default="https://gpt-agent.cc/v1")
    llm_model    = Column(String(64), nullable=True, default="deepseek-v4-flash")

    tasks = relationship("EvalTask", back_populates="owner", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# EvalTask：一次评测任务（对应一批指令）
# ─────────────────────────────────────────────

class EvalTask(Base):
    __tablename__ = "eval_tasks"

    id          = Column(String(36), primary_key=True, default=_uuid)
    owner_id    = Column(String(36), ForeignKey("users.id"), nullable=False)
    name        = Column(String(128), nullable=False)
    status      = Column(String(16), default="pending")  # pending/running/done/failed
    progress    = Column(Integer, default=0)   # 0~100
    total_sessions = Column(Integer, default=0)
    done_sessions  = Column(Integer, default=0)

    # LLM 配置（每次任务可以用不同 key/模型）
    llm_api_key  = Column(String(256), nullable=True)
    llm_base_url = Column(String(256), nullable=True)
    llm_model    = Column(String(64), nullable=True)

    # 指令原始内容（JSON list）
    instructions_json = Column(JSON, nullable=True)

    created_at  = Column(DateTime, default=datetime.utcnow)
    started_at  = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_msg   = Column(Text, nullable=True)

    owner    = relationship("User", back_populates="tasks")
    sessions = relationship("EvalSession", back_populates="task", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# EvalSession：单条对话会话（一轮评测结果）
# ─────────────────────────────────────────────

class EvalSession(Base):
    __tablename__ = "eval_sessions"

    id             = Column(String(36), primary_key=True, default=_uuid)
    task_id        = Column(String(36), ForeignKey("eval_tasks.id"), nullable=False)
    session_id     = Column(String(64), nullable=False)  # 原始 session_id
    instruction_id = Column(Integer, nullable=True)
    persona        = Column(String(64), nullable=True)
    total_turns    = Column(Integer, default=0)
    agent_turns    = Column(Integer, default=0)
    final_score    = Column(Float, default=0.0)
    grade          = Column(String(4), default="F")
    review_flag    = Column(Boolean, default=False)
    review_reason  = Column(Text, nullable=True)
    review_status  = Column(String(16), default="pending")  # pending/approved/rejected
    review_comment = Column(Text, nullable=True)  # 人工审核备注
    review_by      = Column(String(64), nullable=True)  # 审核人用户名

    # 完整评测结果 JSON（包含 dimension_scores / turn_analyses / recommendations）
    result_json    = Column(JSON, nullable=True)

    created_at     = Column(DateTime, default=datetime.utcnow)

    task = relationship("EvalTask", back_populates="sessions")
