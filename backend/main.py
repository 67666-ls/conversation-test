"""
后端启动入口：python main.py 或 uvicorn main:app --reload
"""
import sys
import os

# 确保 backend/ 目录在 sys.path 中，相对导入才能正常工作
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from app import app  # noqa

# 事件循环注入已由 app/__init__.py 的 lifespan 事件处理，无需在此重复

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8088,
        reload=True,
        log_level="info",
    )
