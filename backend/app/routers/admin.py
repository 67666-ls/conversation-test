"""
管理后台路由 — 仅管理员可访问（is_admin=True）
提供：用户列表、任务统计、全局使用概览、批量删除
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, EvalTask, EvalSession
from ..services.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── 权限检查依赖 ──────────────────────────────────────────────────────────────

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """只允许 is_admin=True 的用户，其他人一律 403。"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限：仅管理员可访问此接口",
        )
    return current_user


# ── 概览统计 ──────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """返回全局使用统计（用户数、任务数、会话数、近7天活跃用户数）"""
    total_users    = db.query(func.count(User.id)).scalar()
    total_tasks    = db.query(func.count(EvalTask.id)).scalar()
    total_sessions = db.query(func.count(EvalSession.id)).scalar()

    # 近 7 天有提交任务的用户数
    week_ago = datetime.utcnow() - timedelta(days=7)
    active_users_7d = (
        db.query(func.count(func.distinct(EvalTask.owner_id)))
        .filter(EvalTask.created_at >= week_ago)
        .scalar()
    )

    # 近 7 天每天任务数（用于趋势图）
    daily_tasks = []
    for i in range(6, -1, -1):
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
        day_end   = day_start + timedelta(days=1)
        count = (
            db.query(func.count(EvalTask.id))
            .filter(EvalTask.created_at >= day_start, EvalTask.created_at < day_end)
            .scalar()
        )
        daily_tasks.append({
            "date":  day_start.strftime("%m/%d"),
            "count": count,
        })

    return {
        "total_users":      total_users,
        "total_tasks":      total_tasks,
        "total_sessions":   total_sessions,
        "active_users_7d":  active_users_7d,
        "daily_tasks":      daily_tasks,
    }


# ── 用户列表 ──────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页返回用户列表，含每个用户的任务数和最近活跃时间"""
    q = db.query(User)
    if search:
        q = q.filter(
            User.username.ilike(f"%{search}%") | User.email.ilike(f"%{search}%")
        )

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for u in users:
        task_count = db.query(func.count(EvalTask.id)).filter(EvalTask.owner_id == u.id).scalar()
        last_task = (
            db.query(EvalTask.created_at)
            .filter(EvalTask.owner_id == u.id)
            .order_by(EvalTask.created_at.desc())
            .first()
        )
        result.append({
            "id":          u.id,
            "username":    u.username,
            "email":       u.email,
            "is_admin":    u.is_admin,
            "is_active":   u.is_active,
            "created_at":  u.created_at.isoformat() if u.created_at else None,
            "task_count":  task_count,
            "last_active": last_task[0].isoformat() if last_task else None,
        })

    return {"users": result, "total": total, "page": page, "page_size": page_size}


# ── 全部任务列表 ──────────────────────────────────────────────────────────────

@router.get("/tasks")
def list_all_tasks(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页返回所有用户的任务（含任务名、提交者、状态、会话数、平均分）"""
    q = db.query(EvalTask)
    if status_filter:
        q = q.filter(EvalTask.status == status_filter)

    total = q.count()
    tasks = q.order_by(EvalTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for t in tasks:
        owner = db.query(User.username).filter(User.id == t.owner_id).scalar()
        session_count = db.query(func.count(EvalSession.id)).filter(EvalSession.task_id == t.id).scalar()
        avg_score = (
            db.query(func.avg(EvalSession.final_score))
            .filter(EvalSession.task_id == t.id)
            .scalar()
        )
        result.append({
            "id":            t.id,
            "name":          t.name,
            "owner":         owner,
            "status":        t.status,
            "created_at":    t.created_at.isoformat() if t.created_at else None,
            "session_count": session_count,
            "avg_score":     round(float(avg_score), 2) if avg_score else None,
        })

    return {"tasks": result, "total": total, "page": page, "page_size": page_size}


# ── 封禁/解封用户 ─────────────────────────────────────────────────────────────

@router.post("/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """封禁或解封指定用户（管理员自身不能自我封禁）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, "不能封禁自己")
    user.is_active = not user.is_active
    db.commit()
    return {"id": user.id, "username": user.username, "is_active": user.is_active}


# ── 批量删除任务（管理员）───────────────────────────────────────────────────────

@router.post("/tasks/batch-delete")
def batch_delete_tasks(
    data: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """管理员批量删除任务（级联删除关联会话）。参数：{ "ids": ["id1","id2"] }"""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "请提供要删除的任务 ID 列表")
    # 先删关联会话，再删任务
    db.query(EvalSession).filter(EvalSession.task_id.in_(ids)).delete(synchronize_session="fetch")
    deleted = db.query(EvalTask).filter(EvalTask.id.in_(ids)).delete(synchronize_session="fetch")
    db.commit()
    return {"deleted": deleted}


# ── 删除单个任务（管理员）───────────────────────────────────────────────────────

@router.delete("/tasks/{task_id}")
def admin_delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """管理员删除指定任务及其关联会话"""
    db.query(EvalSession).filter(EvalSession.task_id == task_id).delete()
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    db.delete(task)
    db.commit()
    return {"msg": "已删除"}
