# Data Governance RAG — Docker 镜像
# 国内部署：基础镜像用华为云源（docker.io 被墙），pip 用阿里云源
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim

WORKDIR /app

# 时区（避免日志/时间偏差）
ENV TZ=Asia/Shanghai

# 先复制依赖文件，利用层缓存
COPY requirements.txt .

# 安装依赖（阿里云 pip 源）
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com

# 复制项目代码
COPY . .

# 启动命令（默认跑 ingest 灌库 + 问答验证，可按需覆盖）
CMD ["python", "-m", "ingest.ingest"]