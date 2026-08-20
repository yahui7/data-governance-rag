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


def get_collections():
    """获取两个 Chroma collection（父块 + 子块）"""
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    child = client.get_or_create_collection("governance_child")
    parent = client.get_or_create_collection("governance_parent")
    return child, parent


def retrieve(query: str, top_k: int = None, parent_top_k: int = None) -> list[dict]:
    """
    混合检索（hybrid）：
      ① 父块直接检索 → 命中"总览"类父块，得到完整全貌
      ② 子块检索 → 命中精确细节，映射回父块取全文
      两者合并、按父块去重，父块命中的排前面。

    返回:
        [{text, source, path, parent_id}]
    """
    top_k = top_k or RETRIEVER_CONFIG["top_k"]
    parent_top_k = parent_top_k or RETRIEVER_CONFIG.get("parent_top_k", 3)
    child_col, parent_col = get_collections()

    q = embed_query(query)
    chunks = []
    seen_parent_ids = set()

    # ---------- ① 父块检索（总览问题直接命中父块） ----------
    try:
        parent_results = parent_col.query(
            query_embeddings=[q],
            n_results=parent_top_k,
        )
        for i, pid in enumerate(parent_results["ids"][0]):
            meta = parent_results["metadatas"][0][i]
            doc = parent_results["documents"][0][i]
            if pid in seen_parent_ids:
                continue
            seen_parent_ids.add(pid)
            chunks.append({
                "text": doc,
                "source": meta.get("source", ""),
                "path": meta.get("path", ""),
                "parent_id": pid,
            })
    except Exception as e:
        print(f"⚠️ 父块检索失败: {e}")

    # ---------- ② 子块检索 → 映射父块 ----------
    try:
        child_results = child_col.query(
            query_embeddings=[q],
            n_results=top_k,
        )
        for meta in child_results["metadatas"][0]:
            pid = meta.get("parent_id", "")
            if not pid or pid in seen_parent_ids:
                continue
            parent = get_parent(pid)
            if parent:
                seen_parent_ids.add(pid)
                chunks.append({
                    "text": parent["parent_text"],
                    "source": parent["source"],
                    "path": parent["path"],
                    "parent_id": pid,
                })
    except Exception as e:
        print(f"⚠️ 子块检索失败: {e}")

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

    # 溯源去重：同一文档只显示一次（保持首次出现顺序）
    sources = []
    seen_sources = set()
    for c in chunks:
        if c["source"] in seen_sources:
            continue
        seen_sources.add(c["source"])
        sources.append({"source": c["source"], "path": c["path"]})
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