"""
RAG 查询流水线
query embedding → Chroma 检索 → 拼 prompt → qwen-max 生成（带溯源）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CHROMA_DIR, PROMPT_PATH, RETRIEVER_CONFIG, DASHSCOPE_CONFIG,
)
from rag.embeddings import embed_query


def get_collection():
    """获取 Chroma collection"""
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection(
        name="governance_methodology",
    )


def retrieve(query: str, top_k: int = None) -> list[dict]:
    """
    向量检索：query → embedding → Chroma top_k。

    返回:
        [{text, source, path, score}]
    """
    top_k = top_k or RETRIEVER_CONFIG["top_k"]
    collection = get_collection()

    q = embed_query(query)
    results = collection.query(
        query_embeddings=[q],
        n_results=top_k,
    )

    chunks = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        dist = results["distances"][0][i]
        chunks.append({
            "text": doc,
            "source": meta.get("source", ""),
            "path": meta.get("path", ""),
            "score": dist,   # Chroma 默认 L2 距离，越小越近
        })
    return chunks


def build_prompt(query: str, chunks: list[dict]) -> str:
    """把检索结果拼进系统提示词的 {context}"""
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # 拼接检索上下文（带出处）
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

    返回:
        {"answer": str, "sources": [...]}
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