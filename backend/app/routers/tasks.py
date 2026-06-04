"""
路由：评测任务管理 + WebSocket 实时进度 + 文件上传解析
"""
import asyncio
import io
import json as _json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, BackgroundTasks
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, EvalTask, EvalSession
from ..schemas import TaskCreate, TaskOut, SessionOut, AggregateReport, ReviewSubmit
from ..services.auth import get_current_user
from ..services.eval_service import ws_manager, _run_eval_sync
from ..services.evaluator import _score_to_grade

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
_executor = ThreadPoolExecutor(max_workers=4)


# ─── 文件解析（Excel / TXT / JSON） ───

@router.post("/parse-file")
async def parse_instruction_file(
    file: UploadFile = File(...),
    current_user: "User" = Depends(get_current_user),
):
    """
    上传文件，返回解析后的 instructions 数组。
    支持：
      - .xlsx / .xls：第一列为指令内容（跳过表头行）
      - .txt：用 \\n---\\n 分隔的多段文本
      - .json：本身就是 [{id, instruction}] 数组
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower()
    raw = await file.read()

    instructions = []

    if ext in ("xlsx", "xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            # 自动检测表头：第一行是否全为字符串且不像指令内容
            start = 0
            if rows and rows[0] and isinstance(rows[0][0], str) and len(rows[0][0]) < 50:
                start = 1  # 跳过表头
            for i, row in enumerate(rows[start:], start=1):
                # 优先取第一列；若有第二列且第一列是序号则取第二列
                if not row:
                    continue
                content = None
                if len(row) >= 2 and isinstance(row[0], (int, float)):
                    # 第一列是数字序号，内容在第二列
                    content = str(row[1]).strip() if row[1] else None
                else:
                    content = str(row[0]).strip() if row[0] else None
                if content:
                    instructions.append({"id": i, "instruction": content})
        except ImportError:
            raise HTTPException(500, "服务器未安装 openpyxl，无法解析 Excel 文件")
        except Exception as e:
            raise HTTPException(400, f"Excel 解析失败：{e}")

    elif ext == "txt":
        text = raw.decode("utf-8", errors="replace")
        segs = [s.strip() for s in text.split("\n---\n") if s.strip()]
        instructions = [{"id": i + 1, "instruction": seg} for i, seg in enumerate(segs)]

    elif ext == "json":
        try:
            data = _json.loads(raw)
            arr = data if isinstance(data, list) else [data]
            for i, item in enumerate(arr):
                instructions.append({
                    "id": item.get("id", i + 1),
                    "instruction": item.get("instruction") or item.get("content") or str(item),
                })
        except Exception as e:
            raise HTTPException(400, f"JSON 解析失败：{e}")

    else:
        raise HTTPException(400, "不支持的文件格式，请使用 .xlsx / .txt / .json")

    if not instructions:
        raise HTTPException(400, "文件内容为空，未解析到任何指令")

    return {"instructions": instructions, "count": len(instructions)}


# ─── 创建任务 ───

@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    data: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = EvalTask(
        owner_id=current_user.id,
        name=data.name,
        llm_api_key=data.llm_api_key,
        llm_base_url=data.llm_base_url,
        llm_model=data.llm_model,
        instructions_json=data.instructions,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 后台线程跑评测
    def _on_done(fut):
        exc = fut.exception()
        if exc:
            import traceback
            print(f"[TASKS] 评测线程异常: {exc}")
            traceback.print_exception(type(exc), exc, exc.__traceback__)

    future = _executor.submit(
        _run_eval_sync,
        task.id,
        data.instructions,
        data.llm_api_key,
        data.llm_base_url,
        data.llm_model,
    )
    future.add_done_callback(_on_done)
    return task


# ─── 任务列表 ───

@router.get("", response_model=List[TaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(EvalTask)
        .filter(EvalTask.owner_id == current_user.id)
        .order_by(EvalTask.created_at.desc())
        .all()
    )


# ─── 任务详情 ───

@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(EvalTask).filter(
        EvalTask.id == task_id,
        EvalTask.owner_id == current_user.id,
    ).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


# ─── 任务结果列表 ───

@router.get("/{task_id}/sessions", response_model=List[SessionOut])
def get_sessions(
    task_id: str,
    review_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(EvalTask).filter(
        EvalTask.id == task_id,
        EvalTask.owner_id == current_user.id,
    ).first()
    if not task:
        raise HTTPException(404, "任务不存在")

    q = db.query(EvalSession).filter(EvalSession.task_id == task_id)
    if review_only:
        q = q.filter(EvalSession.review_flag == True,
                     EvalSession.review_status == "pending")
    return q.order_by(EvalSession.created_at.asc()).all()


# ─── 汇总报告 ───

@router.get("/{task_id}/report", response_model=AggregateReport)
def get_report(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(EvalTask).filter(
        EvalTask.id == task_id,
        EvalTask.owner_id == current_user.id,
    ).first()
    if not task:
        raise HTTPException(404, "任务不存在")

    sessions = db.query(EvalSession).filter(EvalSession.task_id == task_id).all()
    if not sessions:
        raise HTTPException(404, "暂无评测结果")

    scores = [s.final_score for s in sessions]
    grades = [s.grade for s in sessions]
    review_count = sum(1 for s in sessions if s.review_flag)

    by_persona: dict = {}
    for s in sessions:
        key = s.persona or "unknown"
        by_persona.setdefault(key, []).append(s.final_score)
    by_persona = {k: {"avg": round(sum(v)/len(v), 2), "count": len(v)} for k, v in by_persona.items()}

    # 维度平均分（从 result_json 提取）
    # result_json 新版格式：{"dimensions": {"task_completion": {"score":80,"reason":"..."}, ...}, ...}
    # result_json 旧版格式：{"dimensions": {"task_completion": 80, ...}, "dialog": [...], ...}
    # result_json 更旧格式：{"dimension_scores": [{"dimension":"xxx","score":N}], ...}
    dim_totals: dict = {}
    dim_counts: dict = {}
    for s in sessions:
        if s.result_json:
            dims = s.result_json.get("dimensions") or s.result_json.get("dimension_scores")
            if dims:
                if isinstance(dims, dict):
                    for dim, val in dims.items():
                        # 新版：val = {"score": 80, "reason": "..."}
                        # 旧版：val = 80
                        score = val["score"] if isinstance(val, dict) else val
                        dim_totals[dim] = dim_totals.get(dim, 0) + score
                        dim_counts[dim] = dim_counts.get(dim, 0) + 1
                elif isinstance(dims, list):
                    # 旧版：[{dimension: "xxx", score: N}]
                    for d in dims:
                        dim = d.get("dimension") or d.get("dim")
                        score = d.get("score", 0)
                        if dim:
                            dim_totals[dim] = dim_totals.get(dim, 0) + score
                            dim_counts[dim] = dim_counts.get(dim, 0) + 1
    dimension_avg = {dim: round(dim_totals[dim] / dim_counts[dim], 3)
                     for dim in dim_totals}

    return AggregateReport(
        total_sessions=len(sessions),
        review_count=review_count,
        overall_avg_score=round(sum(scores)/len(scores), 2),
        overall_max_score=round(max(scores), 2),
        overall_min_score=round(min(scores), 2),
        grade_distribution={g: grades.count(g) for g in "ABCDF"},
        by_persona=by_persona,
        dimension_avg=dimension_avg,
    )


# ─── 删除任务 ───

@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(EvalTask).filter(
        EvalTask.id == task_id,
        EvalTask.owner_id == current_user.id,
    ).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    # 级联删除关联的会话记录
    db.query(EvalSession).filter(EvalSession.task_id == task_id).delete()
    db.delete(task)
    db.commit()
    return {"msg": "已删除"}


# ─── 单条会话详情（审核页弹窗用，返回完整 result_json）───

@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(EvalSession)
        .join(EvalTask, EvalSession.task_id == EvalTask.id)
        .filter(EvalSession.id == session_id, EvalTask.owner_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(404, "会话不存在或无权访问")
    return session


# ─── 批量删除会话（审核页用）───

@router.post("/sessions/batch-delete")
def batch_delete_sessions(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量删除会话。仅允许删除自己名下任务的会话。
    参数：{ "ids": ["id1", "id2", ...] }
    """
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "请提供要删除的会话 ID 列表")
    # 安全：只删除属于当前用户任务的会话
    deleted = (
        db.query(EvalSession)
        .join(EvalTask, EvalSession.task_id == EvalTask.id)
        .filter(EvalSession.id.in_(ids), EvalTask.owner_id == current_user.id)
        .delete(synchronize_session="fetch")
    )
    db.commit()
    return {"deleted": deleted}


# ─── 人工审核提交 ───

@router.post("/sessions/{session_id}/review")
def submit_review(
    session_id: str,
    data: ReviewSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    提交人工审核结果。
    action: approve(通过) / reject(驳回) / override(修改分数)
    只有当前任务的 owner 可以审核。
    """
    session = (
        db.query(EvalSession)
        .join(EvalTask, EvalSession.task_id == EvalTask.id)
        .filter(EvalSession.id == session_id, EvalTask.owner_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(404, "会话不存在或无权访问")

    session.review_status = "approved" if data.action == "approve" else "rejected"
    session.review_comment = data.comment
    session.review_by = current_user.username

    if data.action == "override" and data.score_overrides:
        # 修改分数：更新 result_json 中的维度分数
        rj = session.result_json or {}
        dims = rj.get("dimensions", {})
        for dim, new_score in data.score_overrides.items():
            if dim in dims:
                if isinstance(dims[dim], dict):
                    dims[dim]["score"] = float(new_score)
                    dims[dim]["reason"] = dims[dim].get("reason", "") + f" [人工修正: {current_user.username}]"
                else:
                    dims[dim] = float(new_score)
        # 重新计算总分和等级
        weights = {"task_completion": 0.35, "communication": 0.25, "compliance": 0.20,
                   "efficiency": 0.10, "user_experience": 0.10}
        new_final = 0.0
        for dim, w in weights.items():
            val = dims.get(dim, {})
            s = val["score"] if isinstance(val, dict) else val
            new_final += s * w
        session.final_score = round(new_final, 2)
        # 等级映射
        from ..services.evaluator import _score_to_grade
        session.grade = _score_to_grade(new_final)
        session.review_status = "approved"
        session.review_comment = (data.comment or "") + f" [改分: {data.score_overrides}]"
        if session.review_comment.startswith(" [") and not data.comment:
            session.review_comment = f"分数修正: {data.score_overrides}"
        session.result_json = rj

    db.commit()
    db.refresh(session)
    return {
        "msg": "审核完成",
        "session_id": session.session_id,
        "review_status": session.review_status,
        "final_score": session.final_score,
        "grade": session.grade,
    }


# ─── WebSocket 实时进度 ───

@router.websocket("/{task_id}/ws")
async def task_ws(
    task_id: str,
    websocket: WebSocket,
    db: Session = Depends(get_db),
):
    await ws_manager.connect(task_id, websocket)
    try:
        # 先推一次当前状态
        task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
        if task:
            await websocket.send_json({
                "type": "status",
                "task_id": task_id,
                "status": task.status,
                "progress": task.progress,
                "done": task.done_sessions,
                "total": task.total_sessions,
            })
        # 保持连接直到客户端断开
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id, websocket)
