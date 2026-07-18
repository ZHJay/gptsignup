# Layer: L1 积木层（部署边界）
# Contract: 可重复构建的浏览器注册镜像；密钥通过 env_file/volume 注入。
# Why: 新流程依赖 Playwright；CF 对纯 headless 不友好，默认 xvfb 有头 Chromium。
# Risk: 镜像体积大；小站内存紧时并发保持 1。

FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    BROWSER_HEADLESS=0 \
    BROWSER_CHANNEL=chromium

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY chatgpt.py .
COPY g ./g
COPY deploy/run-browser.sh /usr/local/bin/run-browser.sh
RUN chmod +x /usr/local/bin/run-browser.sh \
    && mkdir -p /app/keys \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

# xvfb 有头 Chromium，降低 CF 拦 headless 概率
ENTRYPOINT ["run-browser.sh"]
CMD ["--yes", "-w", "1", "-n", "1"]
