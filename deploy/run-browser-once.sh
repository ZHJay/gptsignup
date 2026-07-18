#!/usr/bin/env bash
# Layer: L1 积木层（VDS 入口）
# Contract: xvfb 有头 Chromium/Chrome 跑一轮注册+导入；默认不 hold。
# Why: VDS 无显示；BROWSER_HOLD=0 避免无值守挂死。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export BROWSER_HEADLESS="${BROWSER_HEADLESS:-0}"
export BROWSER_CHANNEL="${BROWSER_CHANNEL:-chrome}"
export BROWSER_HOLD="${BROWSER_HOLD:-0}"
export GPT_WORKERS=1

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  alias python=python3
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3 || command -v python)"
fi

if command -v xvfb-run >/dev/null 2>&1; then
  exec xvfb-run -a --server-args="-screen 0 1280x900x24" \
    "$PY" chatgpt.py --yes -w 1 "$@"
else
  echo "[!] xvfb-run 不存在，直接跑（无显示环境可能失败）"
  exec "$PY" chatgpt.py --yes -w 1 "$@"
fi
