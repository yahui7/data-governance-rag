"""
通义千问 Embedding 封装（DashScope OpenAI 兼容接口）
"""

from openai import OpenAI

from config import DASHSCOPE_CONFIG


def get_embedding_client() -> OpenAI:
    """获取 embedding 客户端"""
    return OpenAI(
        api_key=DASHSCOPE_CONFIG["api_key"],
        base_url=DASHSCOPE_CONFIG["base_url"],
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量向量化文本。

    参数:
        texts: 文本列表

    返回:
        list[list[float]]，每个文本一个向量
    """
    if not texts:
        return []

    client = get_embedding_client()
    response = client.embeddings.create(
        model=DASHSCOPE_CONFIG["embedding_model"],
        input=texts,
    )
    # 按输入顺序取向量
    vectors = [item.embedding for item in response.data]
    return vectors


def embed_query(text: str) -> list[float]:
    """向量化单个查询（与 embed_texts 一致，但只处理一条）"""
    return embed_texts([text])[0]