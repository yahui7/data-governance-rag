"""
RAG 查询流水线（small-to-big）
query embedding → Chroma 检索子块 → 映射父块 → 取父块全文 → LLM（带溯源）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CHROMA_DIR, PROMPT_PATH, RETRIEVER_CONFIG, DASHSCOPE_CONFIG,
)
from ingest.docstore import get_parent
from rag.embeddings import embed_query


def get_collection():
    """获取 Chroma collection（只存子块）"""
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection("governance_methodology")


def retrieve(query: str, top_k: int = None) -> list[dict]:
    """
    small-to-big 检索：
      1. 在 Chroma 里检索子块（精确命中）
      2. 每个命中子块映射回父块，取父块全文
      3. 按父块去重（多个子块命中同一父块，合并）

    返回:
        [{text, source, path, parent_id}]
    """
    top_k = top_k or RETRIEVER_CONFIG["top_k"]
    collection = get_collection()

    q = embed_query(query)
    results = collection.query(
        query_embeddings=[q],
        n_results=top_k,
    )

    # 收集命中子块的 parent_id
    parent_ids = []
    for meta in results["metadatas"][0]:
        pid = meta.get("parent_id", "")
        if pid:
            parent_ids.append(pid)

    # 去重 + 从 SQLite 取父块全文
    seen = set()
    chunks = []
    for pid in parent_ids:
        if pid in seen:
            continue
        seen.add(pid)
        parent = get_parent(pid)
        if parent:
            chunks.append({
                "text": parent["parent_text"],
                "source": parent["source"],
                "path": parent["path"],
                "parent_id": pid,
            })

    return chunks


def build_prompt(query: str, chunks: list[dict]) -> str:
    """把父块全文拼进系统提示词的 {context}"""
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    context_parts = []
    for i, chunk in enumerate(chunks):
        context_parts.append(f"【片段{i+1}】来源:《{chunk['source']}》\n{chunk['text']}")

    context = "\n\n".join(context_parts)
    system_prompt = system_prompt.replace("{context}", context)
    return system_prompt


def generate(system_prompt: str, query: str) -> str:
    """调用通义千问生成回答"""
    from openai import OpenAI
    client = OpenAI(
        api_key=DASHSCOPE_CONFIG["api_key"],
        base_url=DASHSCOPE_CONFIG["base_url"],
    )

    response = client.chat.completions.create(
        model=DASHSCOPE_CONFIG["chat_model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=DASHSCOPE_CONFIG["temperature"],
        max_tokens=DASHSCOPE_CONFIG["max_tokens"],
    )
    return response.choices[0].message.content or ""


def ask(query: str) -> dict:
    """
    完整 RAG 问答：检索 → 生成 → 返回答案 + 溯源。
    """
    chunks = retrieve(query)

    if not chunks:
        return {"answer": "知识库中未找到相关内容，请换个问法。", "sources": []}

    system_prompt = build_prompt(query, chunks)
    answer = generate(system_prompt, query)

    sources = [
        {"source": c["source"], "path": c["path"]}
        for c in chunks
    ]
    return {"answer": answer, "sources": sources}


if __name__ == "__main__":
    # 命令行测试
    while True:
        q = input("\n❓ 请输入问题（q 退出）: ").strip()
        if not q or q.lower() == "q":
            break
        result = ask(q)
        print("\n" + "=" * 50)
        print(result["answer"])
        print("\n--- 溯源 ---")
        for s in result["sources"]:
            print(f"  📄 {s['source']}")
        print("=" * 50)