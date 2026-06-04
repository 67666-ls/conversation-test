"""
应用配置 — 全部从环境变量读取，开发时用 .env 文件
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── 数据库 ──
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'data' / 'dialog_eval.db'}"
)

# ── JWT ──
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24h

# ── LLM 默认值（用户可覆盖）──
DEFAULT_LLM_BASE_URL = os.getenv("DEFAULT_LLM_BASE_URL", "https://gpt-agent.cc/v1")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "deepseek-v4-flash")

# ── 评测限制 ──
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "5"))

# ── CORS ──
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
