# Layer: L0 公理层
# Contract: Chrome 指纹头模板；OpenAI Auth 期望 Datadog trace 字段。
# Boundary: 仅构造 header dict，不发 HTTP。

from __future__ import annotations

import random
import uuid

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
SEC_CH_UA_FULL = (
    '"Chromium";v="124.0.0.0", "Not-A.Brand";v="99.0.0.0", '
    '"Google Chrome";v="124.0.0.0"'
)

# Why: Codex CLI client 在 JP 出口会强制 add-phone；platform client 可直接 about-you。
OAUTH_CLIENT_ID = "app_2SKx67EdpoN0G6j64rFvigXD"
OAUTH_REDIRECT_URI = "https://platform.openai.com/auth/callback"
OAUTH_SCOPE = "openid profile email offline_access"
OAUTH_AUDIENCE = "https://api.openai.com/v1"
# Auth0 client metadata used by platform web
AUTH0_CLIENT = (
    "eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjIuMS4yIn0="
)

AUTH_BASE = "https://auth.openai.com"
PLATFORM_BASE = "https://platform.openai.com"
CHAT_BASE = "https://chatgpt.com"
SESSION_URL = f"{CHAT_BASE}/api/auth/session"
SENTINEL_URL = "https://sentinel.openai.com/backend-api/sentinel/req"

# Why: 实测 chrome136 对 auth.openai.com 易 403，chrome124 更稳。
IMPERSONATE_CANDIDATES = ("chrome124", "chrome120", "chrome131", "chrome136")


def json_headers(referer: str, device_id: str) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": AUTH_BASE,
        "referer": referer,
        "oai-device-id": device_id,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": USER_AGENT,
    }
    headers.update(_trace_headers())
    return headers


def navigate_headers(referer: str = "") -> dict[str, str]:
    headers = {
        "accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": USER_AGENT,
    }
    if referer:
        headers["referer"] = referer
    return headers


def chat_session_headers(access_hint: str = "") -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "referer": f"{CHAT_BASE}/",
        "origin": CHAT_BASE,
        "user-agent": USER_AGENT,
        "cache-control": "no-cache",
        "pragma": "no-cache",
    }
    if access_hint:
        headers["authorization"] = f"Bearer {access_hint}"
    return headers


def _trace_headers() -> dict[str, str]:
    parent = str(random.getrandbits(64))
    return {
        "traceparent": f"00-{uuid.uuid4().hex}-{format(int(parent), '016x')}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": str(random.getrandbits(64)),
    }
