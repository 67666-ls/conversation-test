"""
数据库引擎 + Session 工厂
SQLAlchemy + SQLite（生产可切 PostgreSQL，只改 DATABASE_URL）
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DATABASE_URL

# SQLite 需要 check_same_thread=False（多线程访问）
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI Depends 注入 — 每个请求一个 Session，用完自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """建表（首次启动或单测 setup 时调用）"""
    from .models import user  # noqa: F401 — 触发 Base 注册（User/EvalTask/EvalSession 都在 user.py）
    Base.metadata.create_all(bind=engine)
