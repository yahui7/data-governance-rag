"""
数据治理 RAG — 集中配置
"""

import os
from dotenv import load_dotenv

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 加载 .env（DASHSCOPE_API_KEY 等）
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ============================================================
# 通义千问 API 配置（DashScope OpenAI 兼容接口）
# ============================================================
DASHSCOPE_CONFIG = {
    "api_key": os.getenv("DASHSCOPE_API_KEY"),
    "base_url": os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "chat_model": os.getenv("DASHSCOPE_CHAT_MODEL", "qwen-max"),
    "embedding_model": os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3"),
    "temperature": 0.1,   # 问答场景低温度，减少幻觉
    "max_tokens": 2000,
}

# ============================================================
# 文档源 & Chroma 路径
# ============================================================
DOCS_DIR = os.path.join(BASE_DIR, "Docs", "raw", "方法论")   # 方法论文档源
TEMPLATES_DIR = os.path.join(BASE_DIR, "Docs", "raw", "模板") # 模板备份（暂不启用工具）

# Chroma 持久化目录（重启不丢）
CHROMA_DIR = os.path.join(
    os.getenv("CHROMA_DIR", os.path.join(BASE_DIR, "data", "chroma"))
)
DB_PATH = os.path.join(BASE_DIR, "data", "governance.db")    # 结构化知识（预留）

# ============================================================
# 检索 & 问答配置
# ============================================================
RETRIEVER_CONFIG = {
    "top_k": 5,             # 检索返回几个 chunk
    "chunk_size": 800,      # 切块长度（标题切块为主，此为兜底）
    "chunk_overlap": 100,   # 切块重叠
}

# RAG 问答系统提示词路径
PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "rag_system.md")