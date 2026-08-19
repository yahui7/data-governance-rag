"""
数据治理知识库 — Web 服务（FastAPI）

启动:
    uvicorn web.app:app --host 0.0.0.0 --port 8766

浏览器打开 http://localhost:8766 即可使用。
"""

import os
import sys

# 确保能导入项目根目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from web.auth import login, get_user_from_token, logout
from rag.pipeline import ask

app = FastAPI(title="数据治理知识库")


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    question: str


# ============================================================
# 认证工具
# ============================================================
def _extract_token(authorization: str | None) -> str:
    """从 Authorization header 提取 token"""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return ""


# ============================================================
# 路由
# ============================================================
@app.get("/", response_class=HTMLResponse)
def index():
    """返回聊天页面"""
    index_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/login")
def login_endpoint(req: LoginRequest):
    """登录"""
    result = login(req.username, req.password)
    if not result:
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)
    return result


@app.post("/logout")
def logout_endpoint(authorization: str = Header(None)):
    """退出登录"""
    logout(_extract_token(authorization))
    return {"ok": True}


@app.post("/chat")
def chat(req: ChatRequest, authorization: str = Header(None)):
    """问答：调用 RAG pipeline，返回答案 + 溯源"""
    if not req.question.strip():
        return JSONResponse({"error": "问题不能为空"}, status_code=400)

    user = get_user_from_token(_extract_token(authorization))
    if not user:
        return JSONResponse({"error": "未登录或登录已过期"}, status_code=401)

    result = ask(req.question)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "user": user["username"],
        "role": user["role"],
    }