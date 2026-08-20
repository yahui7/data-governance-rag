"""
数据治理方法论 → 向量库 灌库脚本

用法:
    python -m ingest.ingest

流程:
    读取 Docs/raw/方法论 → 清洗(去双链/frontmatter) → 标题切块
    → 批量 embedding(DashScope) → 存入 Chroma(持久化)
"""

import os
import sys

# 确保能 import 项目根目录模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DOCS_DIR, CHROMA_DIR, RETRIEVER_CONFIG
from ingest.cleaner import clean_document
from rag.embeddings import embed_texts

# LangChain 标题切块（识别 # ## ### 层级）
from langchain_text_splitters import MarkdownHeaderTextSplitter

# 文档结构与元数据
HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]


def load_documents(docs_dir: str) -> list[dict]:
    """读取目录下所有 .md，返回 [{path, filename, text}]"""
    documents = []
    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(docs_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        documents.append({"path": path, "filename": fname, "text": raw})
    return documents


def split_markdown(text: str) -> list[str]:
    """
    用标题结构切块。

    标题切块的优势：
      - 保留语义完整性（按 ## 小节切，而不是强行按字符数切）
      - 每块有一个明确的标题上下文
    """
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    chunks = splitter.split_text(text)
    return [chunk.page_content for chunk in chunks]


def ingest():
    print("📂 加载方法论文档...")
    docs = load_documents(DOCS_DIR)
    if not docs:
        print("  ❌ Docs/raw/方法论 下没有 .md 文件")
        sys.exit(1)
    print(f"  ✅ 共 {len(docs)} 个文档")

    # 清洗 + 切块 + 收集元数据
    all_chunks = []
    all_metadatas = []
    for doc in docs:
        print(f"  处理: {doc['filename']}")
        clean_text = clean_document(doc["text"])
        chunks = split_markdown(clean_text)
        print(f"    → {len(chunks)} 块")

        for chunk in chunks:
            all_chunks.append(chunk)
            all_metadatas.append({
                "source": doc["filename"],
                "path": doc["path"],
            })

    print(f"\n📊 共 {len(all_chunks)} 个 chunk")

    print("\n🧠 向量化（DashScope text-embedding-v3）...")
    # 分批 embedding：DashScope text-embedding-v3 单次最多 10 条
    batch_size = 10
    all_embeddings = []
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        vecs = embed_texts(batch)
        all_embeddings.extend(vecs)
        print(f"  ✅ {min(i+batch_size, len(all_chunks))}/{len(all_chunks)} 完成")

    print("\n💾 存入 Chroma...")
    
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # 用 document id 记录每个 chunk
    ids = [f"chunk_{i}" for i in range(len(all_chunks))]

    # upsert：清空后重灌（简单幂等）
    collection = client.get_or_create_collection(
        name="governance_methodology",
    )
    # 如果已有，先清空再灌（避免重复，后续再优化增量）
    if collection.count() > 0:
        print("  ⚠️ 已有数据，清空后重灌...")
        collection.delete(ids=[d["id"] for d in collection.get()["ids"]])

    collection.add(
        ids=ids,
        embeddings=all_embeddings,
        documents=all_chunks,
        metadatas=all_metadatas,
    )

    print(f"\n🎉 灌库完成！Chroma 中 chunk 数: {collection.count()}")
    print(f"   持久化路径: {CHROMA_DIR}")


if __name__ == "__main__":
    ingest()