"""
简单 token 认证（token 持久化到 SQLite）

设计（复用 text2sql 项目验证过的方案）：
  - 账号写死在 config.USERS（MVP）
  - token 存 SQLite，多 worker 共享、重启不丢
  - token 带过期时间（默认 7 天）
"""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta

from config import USERS, AUTH_DB_PATH

# token 有效期（天）
TOKEN_TTL_DAYS = 7


def _get_conn() -> sqlite3.Connection:
    """获取认证数据库连接"""
    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """建 token 表（幂等）"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token      TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


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
    now = datetime.now()
    expires = now + timedelta(days=TOKEN_TTL_DAYS)

    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO tokens (token, username, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token, username, now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    return {"token": token, "role": user["role"], "username": username}


def get_user_from_token(token: str) -> dict | None:
    """从 token 解析用户。检查是否存在且未过期。"""
    if not token:
        return None

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT username, expires_at FROM tokens WHERE token = ?",
            (token,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    # 过期检查
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now() > expires_at:
        _delete_token(token)
        return None

    role = USERS[row["username"]]["role"]
    return {"username": row["username"], "role": role}


def logout(token: str) -> None:
    """删除 token"""
    if not token:
        return
    _delete_token(token)


def _delete_token(token: str) -> None:
    """内部：删除 token"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


# 启动时初始化数据库
_init_db()