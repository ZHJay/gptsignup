# Layer: L1 积木层（部署边界）
# Contract: 可重复构建的运行镜像；密钥通过 env_file/volume 注入，不打进镜像。
# Why: 小站 Docker 部署 + push 后重建，保证与 Git 版本一致。

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY chatgpt.py .
COPY g ./g

RUN mkdir -p /app/keys \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

# 默认入口：非交互注册；运行时用 -w/-n 或 GPT_WORKERS/GPT_TOTAL 覆盖
ENTRYPOINT ["python", "chatgpt.py"]
CMD ["--yes", "-w", "3", "-n", "1"]
