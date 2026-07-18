#!/usr/bin/env bash
# Layer: L1 积木层（容器入口）
# Why: 容器内无显示；用 xvfb 跑有头 Chromium 以降低 Cloudflare 拦截。
set -euo pipefail
export BROWSER_HEADLESS="${BROWSER_HEADLESS:-0}"
export BROWSER_CHANNEL="${BROWSER_CHANNEL:-chromium}"
export BROWSER_HOLD="${BROWSER_HOLD:-0}"
exec xvfb-run -a --server-args="-screen 0 1280x900x24" python /app/chatgpt.py "$@"
