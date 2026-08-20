"""
父子切块：父块（##）语义完整，子块（### + 字长兜底）检索精确。

设计：
  父块：按 Markdown 的 # / ## 切，保留标题原文 → 存 docstore(SQLite)
  子块：在父块内，先按 ### 切；若某 ### 段仍超长，再按字长兜底截断
        → 存 Chroma（检索用），metadata 带 parent_id

切块输出结构：
  [
    {
      "parent_id": "...",
      "parent_text": "父块全文（含标题、表格）",
      "children": ["子块1", "子块2", ...]
    },
    ...
  ]
"""

import hashlib
import re

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingest.cleaner import clean_document

# 父块按 ## 切（含 # 根标题）
PARENT_HEADERS = [
    ("#", "h1"),
    ("##", "h2"),
]

# 子块切分：在父块内部，先按 ### 切
CHILD_HEADERS = [
    ("###", "h3"),
]

# 子块兜底字长（### 段超长时再切）
CHILD_CHUNK_SIZE = 500
CHILD_CHUNK_OVERLAP = 50


def _hash(s: str) -> str:
    """依据内容生成稳定 id（内容不变 → id 不变）"""
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


def _clean_markdown_wrapper(text: str) -> str:
    """清洗 Obsidian 双链等（复用 cleaner）"""
    return clean_document(text)


def split_document(raw_text: str, source: str) -> list[dict]:
    """
    将一个文档切成父块 + 子块。

    参数:
        raw_text: 文档原始内容
        source:   文档文件名（用于生成 parent_id 的稳定前缀）

    返回:
        结构见模块 docstring
    """
    text = _clean_markdown_wrapper(raw_text)

    # ---------- 父块：按 # / ## 切 ----------
    parent_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=PARENT_HEADERS,
        strip_headers=False,   # 保留标题，溯源清晰
    )
    try:
        parent_chunks = parent_splitter.split_text(text)
    except Exception:
        # 极少数无标题的文档，退化为整篇一个父块
        parent_chunks = []

    # 如果没有切出任何父块（文档没有标题层级），整篇作为一个父块
    if not parent_chunks:
        parent_chunks = [type("C", (), {"page_content": text})()]

    # ---------- 子块：在父块内按 ### 切 + 字长兜底 ----------
    child_h3_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=CHILD_HEADERS,
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHILD_CHUNK_SIZE,
        chunk_overlap=CHILD_CHUNK_OVERLAP,
    )

    records = []
    for ci, parent_chunk in enumerate(parent_chunks):
        parent_text = parent_chunk.page_content
        parent_id = f"{source}::{_hash(parent_text)}"

        # 子块划分：先在父块内按 ### 切
        children = []
        try:
            h3_chunks = child_h3_splitter.split_text(parent_text)
        except Exception:
            h3_chunks = []

        if h3_chunks:
            for h3 in h3_chunks:
                h3_text = h3.page_content
                # 若 ### 段仍然过长，再按字长兜底
                if len(h3_text) > CHILD_CHUNK_SIZE:
                    children.extend([c.page_content for c in char_splitter.split_text(h3_text)])
                else:
                    children.append(h3_text)
        else:
            # 父块内没有 ###，整个父块作为唯一子块
            children.append(parent_text)

        # 过滤空块
        children = [c for c in children if c.strip()]

        if not children:
            continue

        records.append({
            "parent_id": parent_id,
            "parent_text": parent_text,
            "children": children,
        })

    return records