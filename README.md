# Data Governance RAG

数据治理知识库 — 用 LangChain + 通义千问（DashScope）+ Chroma 搭建的 RAG 问答系统。
覆盖数据治理方法论、实践、问题与解决方案，支持答案溯源。

## 架构

```
用户提问
  ↓
query embedding（DashScope text-embedding-v3）
  ↓
Chroma 向量检索（top-k）
  ↓
拼 prompt（系统提示词 + 检索片段 + 溯源要求）
  ↓
qwen-max 生成回答（带出处引用）
```

```
灌库流程：
Docs/raw/方法论/*.md → 清洗(去双链/frontmatter) → 标题切块
  → embedding → 存入 Chroma（data/chroma 持久化）
```

## 技术选型

| 项 | 选择 | 说明 |
|----|------|------|
| 框架 | LangChain（MarkdownHeaderTextSplitter） | 标题切块，语义完整 |
| embedding | 通义千问 text-embedding-v3 | DashScope OpenAI 兼容接口 |
| 聊天模型 | qwen-max | DashScope OpenAI 兼容接口 |
| 向量库 | Chroma（持久化） | data/chroma 目录 |
| 部署 | Docker | 容器内 python 3.11 |

## 目录结构

```
data-governance-rag/
├── Docs/raw/方法论/    # 原始文档源（方法论文档）
├── Docs/raw/模板/      # 原始模板（暂未启用，预留）
├── ingest/             # 灌库：读取→清洗→切块→embedding→Chroma
│   ├── cleaner.py      # 双链/frontmatter/callout 清洗
│   └── ingest.py       # 灌库主入口
├── rag/
│   ├── embeddings.py   # DashScope embedding 封装
│   └── pipeline.py     # 检索 + 生成（带溯源）
├── prompts/            # 系统提示词
├── data/               # Chroma 持久化目录（运行时生成）
├── api/                #（待开发）FastAPI Web 服务
├── web/                #（待开发）前端
├── config.py           # 集中配置
├── Dockerfile
└── docker-compose.yaml
```

## Docker 使用（虚拟机环境）

### 1. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 DashScope API Key：

```bash
cp .env.example .env
# 然后编辑 .env，填入 DASHSCOPE_API_KEY
```

### 2. 灌库（从 Docs/raw/方法论 → Chroma）

```bash
docker compose run --rm ingest
```

### 3. 单个问题问答测试

```bash
docker compose run --rm ingest python -m rag.pipeline
```

启动后输入问题（如"数据资产盘点的步骤是什么？"），`q` 退出。

## 待开发

- [x] 灌库（方法论 9 个文件）
- [ ] 模板工具（Docs/raw/模板 → 按名调用，不走向量）→ 见后续
- [ ] FastAPI Web 界面 + 登录（复用 text2sql 经验）
- [ ] 部署到 ECS rag.yahui.org.cn
- [ ] RAGAS 评测体系

## 复用经验

部署/国内源（华为云镜像、阿里云 pip）、多进程 token 存储等坑，见
Obsidian「04Agent搭建」下的部署踩坑记录。