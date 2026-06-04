"""
FastAPI 应用入口
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import ALLOWED_ORIGINS
from .database import init_db
from .routers import auth, tasks, admin
from .services import eval_service

# 前端目录（backend/../frontend）
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：建表 + 注入事件循环到 eval_service
    init_db()
    eval_service.set_event_loop(asyncio.get_event_loop())
    yield
    # 关闭时：无需额外清理


app = FastAPI(
    title="AI 外呼评测系统",
    description="多轮对话评测 Web App — 美团AI Hackathon",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ── 前端静态文件（必须放在所有 API 路由之后）──
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"msg": "前端目录不存在，请确认 frontend/ 目录位置", "expected": str(FRONTEND_DIR)}
