"""
路由：用户注册 / 登录 / 配置
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserRegister, UserLogin, Token, UserOut, UserConfigUpdate, LLMTestRequest
from ..services.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserRegister, db: Session = Depends(get_db)):
    # 检查重复
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "用户名已存在")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "邮箱已被注册")

    # 第一个注册的用户自动成为管理员
    is_first_user = db.query(User).count() == 0

    user = User(
        username=data.username,
        email=data.email,
        hashed_pw=hash_password(data.password),
        is_admin=is_first_user,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = create_access_token({"sub": user.id})
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/config", response_model=UserOut)
def update_config(
    data: UserConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存用户的 LLM 配置到账号（跨设备登录自动同步）"""
    if data.llm_api_key is not None:
        current_user.llm_api_key = data.llm_api_key
    if data.llm_base_url is not None:
        current_user.llm_base_url = data.llm_base_url
    if data.llm_model is not None:
        current_user.llm_model = data.llm_model
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/test-llm")
def test_llm(data: LLMTestRequest):
    """
    测试 LLM API 连通性。
    发一条最简单的 "Hello" 请求，返回是否成功及首 token 延迟。
    """
    import http.client
    import json as _json
    import urllib.parse
    import time

    parsed = urllib.parse.urlparse(data.base_url)
    host = parsed.netloc
    path_prefix = parsed.path.rstrip("/")
    endpoint = f"{path_prefix}/chat/completions"

    payload = _json.dumps({
        "model": data.model,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 5,
    }).encode()

    headers = {
        "Authorization": f"Bearer {data.api_key}",
        "Content-Type": "application/json",
    }

    start = time.time()
    try:
        conn = http.client.HTTPSConnection(host, timeout=10)
        conn.request("POST", endpoint, body=payload, headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        latency = round((time.time() - start) * 1000, 1)

        if resp.status != 200:
            return {
                "ok": False,
                "latency_ms": latency,
                "error": f"HTTP {resp.status}: {body[:200]}",
            }

        data_obj = _json.loads(body)
        content = data_obj.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "ok": True,
            "latency_ms": latency,
            "model": data.model,
            "reply": content.strip(),
        }

    except Exception as e:
        latency = round((time.time() - start) * 1000, 1)
        return {
            "ok": False,
            "latency_ms": latency,
            "error": f"连接失败: {str(e)}",
        }
