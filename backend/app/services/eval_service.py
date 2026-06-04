"""
评测服务：异步执行评测 + WebSocket 进度推送

架构：
- FastAPI BackgroundTasks 异步跑评测（零额外依赖）
- WebSocket 连接池：{task_id: [ws1, ws2, ...]}
- 评测进度实时推送到所有监听该 task 的前端连接
"""
import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Dict, List
from fastapi import WebSocket
from sqlalchemy.orm import Session

# 引擎文件已迁移到 services/ 下，直接相对导入
from .user_simulator import InstructionParser, run_simulations, detect_personas  # noqa
from .evaluator import BatchEvaluator, DialogEvaluator  # noqa

from ..models import EvalTask, EvalSession
from ..database import SessionLocal


# ─────────────────────────────────────────────
# WebSocket 连接管理
# ─────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        # task_id → list of active WebSocket connections
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)

    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, task_id: str, message: dict):
        """向所有监听该 task_id 的前端推送消息"""
        conns = self._connections.get(task_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)


ws_manager = ConnectionManager()


# ─────────────────────────────────────────────
# 评测执行（在 BackgroundTask 中运行）
# ─────────────────────────────────────────────

def _run_eval_sync(task_id: str, instructions: list, llm_api_key: str,
                   llm_base_url: str, llm_model: str):
    """
    同步评测逻辑（在线程池中运行，不阻塞事件循环）。
    每完成一条 session 就往数据库写结果，通过 asyncio 异步推进度。
    """
    import traceback
    print(f"[EVAL] 开始评测任务 {task_id}, instructions={len(instructions)}")

    db: Session = None
    try:
        db = SessionLocal()
        task: EvalTask = db.query(EvalTask).filter(EvalTask.id == task_id).first()
        if not task:
            db.close()
            _push_progress(task_id, {"type": "error", "task_id": task_id, "message": "任务记录未找到"})
            print(f"[EVAL] 任务 {task_id} 不存在，退出")
            return

        task.status = "running"
        task.started_at = datetime.utcnow()
        db.commit()
        print(f"[EVAL] 任务 {task_id} 状态设为 running")

        # ── 解析指令 ──
        instructions_map = {}
        for inst in instructions:
            inst_id = inst.get("id", 0)
            instructions_map[inst_id] = InstructionParser.parse(inst.get("instruction", ""))
        print(f"[EVAL] 解析了 {len(instructions_map)} 条指令")

        # ── 智能识别人设 ──
        # 用第一条指令的文本让 LLM 判断该场景最适合哪些人设
        first_inst_text = instructions[0].get("instruction", "") if instructions else ""
        detected_personas = detect_personas(
            first_inst_text,
            llm_api_key, llm_base_url or "https://gpt-agent.cc/v1", llm_model or "deepseek-v4-flash",
        )
        print(f"[EVAL] 检测到 {len(detected_personas)} 种人设")

        # ── 预计算总量 + 注入环境变量 ──
        total_expected = len(instructions) * len(detected_personas)
        task.total_sessions = total_expected
        db.commit()
        print(f"[EVAL] 预计 {total_expected} 条会话 ({len(instructions)} 指令 × {len(detected_personas)} 人设)")

        os.environ["DEEPSEEK_API_KEY"] = llm_api_key or ""
        os.environ["DEEPSEEK_BASE_URL"] = llm_base_url or ""
        os.environ["DEEPSEEK_MODEL"] = llm_model or "deepseek-v4-flash"
        print(f"[EVAL] 注入环境变量: model={llm_model}, key_len={len(llm_api_key or '')}, base_url={llm_base_url}")

        # 进度回调：每生成一条 session 就推一次前端
        def on_session_done(done_count: int):
            task.done_sessions = done_count
            task.progress = int(done_count / total_expected * 100) if total_expected else 0
            db.commit()
            _push_progress(task_id, {
                "type": "progress",
                "task_id": task_id,
                "progress": task.progress,
                "done": done_count,
                "total": total_expected,
            })

        sessions = run_simulations(instructions, personas=detected_personas, progress_callback=on_session_done)
        print(f"[EVAL] 生成 {len(sessions)} 条会话")

        # ── 逐条评测 + 写库 ──
        evaluator = BatchEvaluator(instructions_map)
        for i, session in enumerate(sessions):
            inst_id = session["instruction_id"]
            parsed = instructions_map.get(inst_id, {})
            single_evaluator = DialogEvaluator(parsed)
            result = single_evaluator.evaluate(session)

            # 写入数据库
            eval_session = EvalSession(
                task_id=task_id,
                session_id=result.session_id,
                instruction_id=result.instruction_id,
                persona=result.persona,
                total_turns=result.total_turns,
                agent_turns=result.agent_turns,
                final_score=result.final_score,
                grade=result.grade,
                review_flag=result.review_flag,
                review_reason=result.review_reason,
                result_json=result.to_dict(),
            )
            db.add(eval_session)

            # 更新进度
            task.done_sessions = i + 1
            task.progress = int((i + 1) / len(sessions) * 100)
            db.commit()

            # 异步推 WebSocket
            _push_progress(task_id, {
                "type": "progress",
                "task_id": task_id,
                "progress": task.progress,
                "done": i + 1,
                "total": len(sessions),
                "latest": {
                    "session_id": result.session_id,
                    "persona": result.persona,
                    "grade": result.grade,
                    "score": round(result.final_score, 1),
                    "review_flag": result.review_flag,
                },
            })

        task.status = "done"
        task.progress = 100
        task.finished_at = datetime.utcnow()
        db.commit()
        print(f"[EVAL] 任务 {task_id} 完成")

        _push_progress(task_id, {"type": "done", "task_id": task_id})

    except Exception as e:
        print(f"[EVAL] 任务 {task_id} 异常: {e}")
        traceback.print_exc()
        try:
            if db and task:
                task.status = "failed"
                task.error_msg = str(e)
                db.commit()
                _push_progress(task_id, {"type": "error", "task_id": task_id, "message": str(e)})
        except Exception as db_err:
            print(f"[EVAL] 连 DB 回写也失败了: {db_err}")
    finally:
        if db:
            db.close()
            print(f"[EVAL] 任务 {task_id} DB 连接已关闭")


# 全局事件循环引用（main.py 启动时注入）
_event_loop = None

def set_event_loop(loop):
    global _event_loop
    _event_loop = loop

def _push_progress(task_id: str, message: dict):
    """在同步线程里安全推 WebSocket 消息"""
    if _event_loop and not _event_loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast(task_id, message),
            _event_loop
        )
