# Layer: L1 积木层
# Contract: 在同一 curl_cffi Session 上 GET /api/auth/session，取出 accessToken。
# Why: 相对 Grok 的 sso cookie，ChatGPT 凭据取自 session JSON 的 accessToken。
# Boundary: 不负责登录/注册，只读已有会话态。

from __future__ import annotations

import json
from typing import Any

from .openai_headers import SESSION_URL, chat_session_headers


def fetch_access_token(session, *, access_hint: str = "", timeout: int = 20) -> str:
    """从 https://chatgpt.com/api/auth/session 提取 accessToken。

    Returns:
        非空 accessToken 字符串；失败返回 ""。
    """
    try:
        resp = session.get(
            SESSION_URL,
            headers=chat_session_headers(access_hint),
            timeout=timeout,
            allow_redirects=True,
        )
    except Exception as exc:
        print(f"[-] session 请求异常: {exc}")
        return ""

    if getattr(resp, "status_code", 0) != 200:
        print(f"[-] /api/auth/session HTTP {getattr(resp, 'status_code', '?')}")
        # 仍尝试从 body 抠 token
        text = str(getattr(resp, "text", "") or "")
        return _extract_token_from_text(text)

    data = _as_dict(resp)
    token = str(data.get("accessToken") or data.get("access_token") or "").strip()
    if not token:
        token = _extract_token_from_text(str(getattr(resp, "text", "") or ""))
    return token


def _as_dict(resp) -> dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        text = str(getattr(resp, "text", "") or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _extract_token_from_text(text: str) -> str:
    if not text or "accessToken" not in text:
        return ""
    key = '"accessToken"'
    i = text.find(key)
    if i < 0:
        return ""
    j = text.find(":", i + len(key))
    if j < 0:
        return ""
    rest = text[j + 1 :].lstrip()
    if not rest.startswith('"'):
        return ""
    end = 1
    while end < len(rest):
        if rest[end] == '"' and rest[end - 1] != "\\":
            return rest[1:end]
        end += 1
    return ""
