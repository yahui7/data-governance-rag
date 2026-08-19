"""
简单 token 认证（MVP 阶段，账号写死在 config）
"""

import secrets

from config import USERS

# token -> 用户名（内存存储，MVP 够用；重启失效需重新登录）
TOKEN_STORE: dict[str, str] = {}


def login(username: str, password: str) -> dict | None:
    """
    验证用户名密码。

    成功返回 {"token", "role", "username"}
    失败返回 None
    """
    user = USERS.get(username)
    if not user or user["password"] != password:
        return None

    token = secrets.token_hex(32)
    TOKEN_STORE[token] = username
    return {"token": token, "role": user["role"], "username": username}


def get_user_from_token(token: str) -> dict | None:
    """从 token 解析用户，无效返回 None"""
    username = TOKEN_STORE.get(token)
    if not username:
        return None
    role = USERS[username]["role"]
    return {"username": username, "role": role}


def logout(token: str) -> None:
    """删除 token"""
    TOKEN_STORE.pop(token, None)