# Layer: L1 积木层
# Contract: OAuth 入口 + authorize/continue + 密码注册。
# Boundary: 单步 HTTP，不含 OTP/建号。

from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

from .http_session import is_cloudflare_challenge
from .openai_headers import (
    AUTH0_CLIENT,
    AUTH_BASE,
    OAUTH_AUDIENCE,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPE,
    PLATFORM_BASE,
    USER_AGENT,
    json_headers,
    navigate_headers,
)
from .pkce import generate_pkce
from .sentinel import build_sentinel_token


class RegistrationError(RuntimeError):
    """注册步骤失败。"""


def set_device_cookie(session, device_id: str) -> None:
    for domain in (".auth.openai.com", "auth.openai.com", ".chatgpt.com", "chatgpt.com"):
        try:
            session.cookies.set("oai-did", device_id, domain=domain, path="/")
        except Exception:
            pass


def start_oauth(session, email: str) -> tuple[str, str]:
    """访问 platform OAuth 入口，返回 (code_verifier, device_id_hint)。"""
    code_verifier, challenge = generate_pkce()
    params = {
        "issuer": AUTH_BASE,
        "client_id": OAUTH_CLIENT_ID,
        "audience": OAUTH_AUDIENCE,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": OAUTH_SCOPE,
        "response_type": "code",
        "response_mode": "query",
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "screen_hint": "signup",
        "login_hint": email,
        "prompt": "login",
        "auth0Client": AUTH0_CLIENT,
    }
    url = f"{AUTH_BASE}/api/accounts/authorize?{urlencode(params)}"
    headers = navigate_headers(f"{PLATFORM_BASE}/")
    resp = session.get(url, headers=headers, timeout=30, allow_redirects=True)
    if is_cloudflare_challenge(resp) or resp.status_code >= 400:
        url2 = f"{AUTH_BASE}/oauth/authorize?{urlencode(params)}"
        resp = session.get(url2, headers=headers, timeout=30, allow_redirects=True)
    if is_cloudflare_challenge(resp):
        raise RegistrationError("Cloudflare blocked authorize")
    if resp.status_code >= 400:
        raise RegistrationError(f"authorize HTTP {resp.status_code}")
    did = str(session.cookies.get("oai-did") or "").strip()
    return code_verifier, did


def authorize_continue(session, device_id: str, email: str) -> str:
    url = f"{AUTH_BASE}/api/accounts/authorize/continue"
    headers = json_headers(f"{AUTH_BASE}/create-account", device_id)
    headers["openai-sentinel-token"] = build_sentinel_token(
        session, device_id, "authorize_continue"
    )
    body = {
        "username": {"value": email, "kind": "email"},
        "screen_hint": "signup",
    }
    resp = session.post(url, headers=headers, data=json.dumps(body), timeout=30)
    if resp.status_code != 200:
        raise RegistrationError(
            f"authorize/continue HTTP {resp.status_code}: {_snip(resp)}"
        )
    try:
        data = resp.json() or {}
    except Exception:
        data = {}
    return str((data.get("page") or {}).get("type") or "")


def register_password(session, device_id: str, email: str, password: str) -> None:
    url = f"{AUTH_BASE}/api/accounts/user/register"
    headers = {
        "referer": f"{AUTH_BASE}/create-account/password",
        "accept": "application/json",
        "content-type": "application/json",
        "origin": AUTH_BASE,
        "oai-device-id": device_id,
        "user-agent": USER_AGENT,
    }
    resp = session.post(
        url,
        headers=headers,
        data=json.dumps({"username": email, "password": password}),
        timeout=30,
    )
    if resp.status_code != 200:
        headers["openai-sentinel-token"] = build_sentinel_token(
            session, device_id, "username_password_create"
        )
        resp = session.post(
            url,
            headers=headers,
            data=json.dumps({"username": email, "password": password}),
            timeout=30,
        )
    if resp.status_code != 200:
        raise RegistrationError(f"register HTTP {resp.status_code}: {_snip(resp)}")


def _snip(resp, n: int = 240) -> str:
    try:
        return (resp.text or "")[:n]
    except Exception:
        return ""
