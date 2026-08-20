"""
数据治理方法论 → 向量库 增量灌库脚本

用法:
    python -m ingest.ingest

流程:
    扫描 Docs/raw/方法论 → 对每个文件计算 hash
    → 与 docstore 的 file_index 比对：
        未变 → 跳过（不动，省 token）
        变更 → 删旧 → 切片向量化 → 重新入库
        新增 → 切片向量化 → 入库
    子块 → Chroma（检索用，带 parent_id / source / file_hash）
    父块 → SQLite docstore（取全文用）
"""

import hashlib
import os
import re
import sys

# 确保能 import 项目根目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DOCS_DIR, CHROMA_DIR
from ingest.chunking import split_document
from ingest.docstore import (
    init_db, upsert_parent, delete_parents_by_source,
    get_file_hash, set_file_hash, delete_file_index,
)
from rag.embeddings import embed_texts


def file_hash(path: str) -> str:
    """计算文件内容 hash（增量判断依据）"""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_chroma_collections():
    """
    获取两个 Chroma collection：
      - child:  子块向量（精确检索）
      - parent: 父块向量（总览问题直接命中父块）
    """
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    child = client.get_or_create_collection("governance_child")
    parent = client.get_or_create_collection("governance_parent")
    return child, parent


def delete_source_from_chroma(collections, source: str) -> None:
    """按 source 删除该文档在两个 collection 里的向量（子块+父块）"""
    for coll in collections:
        try:
            coll.delete(where={"source": source})
        except Exception as e:
            print(f"  ⚠️ 删除 {source} 旧向量失败: {e}")


def embed_batch(texts: list[str]) -> list[list[float]]:
    """批量向量化（DashScope 单次最多 10 条）"""
    batch_size = 10
    result = []
    for i in range(0, len(texts), batch_size):
        result.extend(embed_texts(texts[i:i+batch_size]))
    return result


def ingest_one_document(path: str, source: str, child_col, parent_col) -> int:
    """
    处理单个文档：
      子块向量 → Chroma(child_col) 精确检索
      父块向量 → Chroma(parent_col) 总览检索
      父块全文 → SQLite docstore

    返回: 子块总数
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    fhash = file_hash(path)
    records = split_document(raw, source)

    if not records:
        print(f"  ⚠️ {source} 没有切出任何块，跳过")
        return 0

    # ---------- 收集子块 ----------
    all_children = []
    for rec in records:
        for i, child in enumerate(rec["children"]):
            all_children.append({
                "child_id": f"{rec['parent_id']}::c{i}",
                "parent_id": rec["parent_id"],
                "text": child,
            })

    # ---------- 先删旧（两个 collection 都要） ----------
    delete_source_from_chroma([child_col, parent_col], source)

    # ---------- 子块向量化 → Chroma child ----------
    if all_children:
        child_embeds = embed_batch([c["text"] for c in all_children])
        child_col.add(
            ids=[c["child_id"] for c in all_children],
            embeddings=child_embeds,
            documents=[c["text"] for c in all_children],
            metadatas=[
                {
                    "parent_id": c["parent_id"],
                    "source": source,
                    "path": path,
                    "file_hash": fhash,
                }
                for c in all_children
            ],
        )

    # ---------- 父块向量化 → Chroma parent ----------
    parent_texts = [rec["parent_text"] for rec in records]
    parent_embeds = embed_batch(parent_texts)
    parent_col.add(
        ids=[rec["parent_id"] for rec in records],
        embeddings=parent_embeds,
        documents=parent_texts,
        metadatas=[
            {
                "source": source,
                "path": path,
                "file_hash": fhash,
            }
            for _ in records
        ],
    )

    # ---------- 父块全文 → SQLite docstore ----------
    for rec in records:
        rec["source"] = source
        rec["path"] = path
        rec["file_hash"] = fhash
        rec["child_ids"] = [
            c["child_id"]
            for c in all_children
            if c["parent_id"] == rec["parent_id"]
        ]
        upsert_parent(rec)

    return len(all_children)


def ingest():
    print("📂 初始化...")
    init_db()
    child_col, parent_col = get_chroma_collections()

    if not os.path.isdir(DOCS_DIR):
        print(f"❌ 文档目录不存在: {DOCS_DIR}")
        sys.exit(1)

    # 收集目录里所有 .md
    files = sorted(
        f for f in os.listdir(DOCS_DIR)
        if f.endswith(".md")
    )
    print(f"📄 发现 {len(files)} 个文档\n")

    stats = {"new": 0, "changed": 0, "skipped": 0}
    for source in files:
        path = os.path.join(DOCS_DIR, source)
        cur_hash = file_hash(path)
        stored_hash = get_file_hash(source)

        if stored_hash == cur_hash:
            print(f"⏭️  跳过（未变）: {source}")
            stats["skipped"] += 1
            continue

        if stored_hash is None:
            action = "新增"
            stats["new"] += 1
        else:
            action = "变更"
            stats["changed"] += 1

        print(f"📥 {action}: {source}")
        n = ingest_one_document(path, source, child_col, parent_col)
        if n > 0:
            set_file_hash(source, cur_hash)
        print(f"    → {n} 子块入库\n")

    print("=" * 40)
    print(f"完成。新增 {stats['new']}，变更 {stats['changed']}，跳过 {stats['skipped']}")
    print(f"Chroma 子块总数: {child_col.count()}，父块总数: {parent_col.count()}")


if __name__ == "__main__":
    ingest()