"""
docstore：父块全文 + 文件增量索引（SQLite 持久化）

两张表：
  parents     父子映射与父块全文
               parent_id PK, source, path, file_hash, parent_text
               child_ids 以逗号分隔存（用于溯源/删除）
  file_index  文件增量判断
               source PK（文档文件名）, file_hash, last_ingested
"""

import json
import os
import sqlite3

# SQLite 文件路径（与 Chroma 分离，放 data/ 下）
DOCSTORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "docstore.db",
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DOCSTORE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表（幂等）"""
    conn = _conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parents (
                parent_id   TEXT PRIMARY KEY,
                source      TEXT NOT NULL,
                path        TEXT,
                file_hash   TEXT,
                parent_text TEXT NOT NULL,
                child_ids   TEXT          -- JSON 数组
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_index (
                source        TEXT PRIMARY KEY,
                file_hash     TEXT NOT NULL,
                last_ingested TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# parents：父块增删查
# ============================================================
def upsert_parent(record: dict) -> None:
    """写入一个父块（含其子块 id 列表）"""
    conn = _conn()
    try:
        conn.execute("""
            INSERT INTO parents (parent_id, source, path, file_hash, parent_text, child_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(parent_id) DO UPDATE SET
              source=excluded.source,
              path=excluded.path,
              file_hash=excluded.file_hash,
              parent_text=excluded.parent_text,
              child_ids=excluded.child_ids
        """, (
            record["parent_id"],
            record["source"],
            record["path"],
            record["file_hash"],
            record["parent_text"],
            json.dumps(record.get("child_ids", []), ensure_ascii=False),
        ))
        conn.commit()
    finally:
        conn.close()


def delete_parents_by_source(source: str) -> None:
    """删除某个来源的所有父块（增量重灌时先清旧）"""
    conn = _conn()
    try:
        conn.execute("DELETE FROM parents WHERE source = ?", (source,))
        conn.commit()
    finally:
        conn.close()


def get_parent(parent_id: str) -> dict | None:
    """按 parent_id 取父块（含子块 id 列表）"""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM parents WHERE parent_id = ?", (parent_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return {
        "parent_id": row["parent_id"],
        "source": row["source"],
        "path": row["path"],
        "file_hash": row["file_hash"],
        "parent_text": row["parent_text"],
        "child_ids": json.loads(row["child_ids"] or "[]"),
    }


# ============================================================
# file_index：增量判断
# ============================================================
def get_file_hash(source: str) -> str | None:
    """取某个文档文件当前入库时的 hash，未入库返回 None"""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT file_hash FROM file_index WHERE source = ?", (source,)
        ).fetchone()
    finally:
        conn.close()
    return row["file_hash"] if row else None


def set_file_hash(source: str, file_hash: str) -> None:
    """记录文档 hash（新增或更新）"""
    from datetime import datetime
    conn = _conn()
    try:
        conn.execute("""
            INSERT INTO file_index (source, file_hash, last_ingested)
            VALUES (?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
              file_hash=excluded.file_hash,
              last_ingested=excluded.last_ingested
        """, (source, file_hash, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def delete_file_index(source: str) -> None:
    """删除某文件的索引（对应文档文件被移除时）"""
    conn = _conn()
    try:
        conn.execute("DELETE FROM file_index WHERE source = ?", (source,))
        conn.commit()
    finally:
        conn.close()