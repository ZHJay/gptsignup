# Layer: L1 积木层
# Contract: OTP、建号、OAuth 换票、chatgpt.com 预热。
# Boundary: 单步 HTTP；add_phone / registration_disallowed 抛可读错误。

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .openai_headers import (
    AUTH0_CLIENT,
    AUTH_BASE,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    PLATFORM_BASE,
    USER_AGENT,
    json_headers,
    navigate_headers,
)
from .openai_auth_entry import RegistrationError, _snip
from .sentinel import build_sentinel_token


def send_otp(session) -> None:
    url = f"{AUTH_BASE}/api/accounts/email-otp/send"
    headers = navigate_headers(f"{AUTH_BASE}/create-account/password")
    resp = session.get(url, headers=headers, timeout=30, allow_redirects=True)
    if resp.status_code not in (200, 302, 400):
        raise RegistrationError(f"send_otp HTTP {resp.status_code}: {_snip(resp)}")


def validate_otp(session, device_id: str, code: str) -> str:
    """校验 OTP，返回下一页 page.type。"""
    url = f"{AUTH_BASE}/api/accounts/email-otp/validate"
    headers = json_headers(f"{AUTH_BASE}/email-verification", device_id)
    resp = session.post(
        url, headers=headers, data=json.dumps({"code": code}), timeout=30
    )
    if resp is None or resp.status_code != 200:
        headers["openai-sentinel-token"] = build_sentinel_token(
            session, device_id, "authorize_continue"
        )
        resp = session.post(
            url, headers=headers, data=json.dumps({"code": code}), timeout=30
        )
    if resp is None or resp.status_code != 200:
        raise RegistrationError(
            f"validate_otp HTTP {getattr(resp, 'status_code', '?')}: {_snip(resp)}"
        )
    try:
        data = resp.json() or {}
    except Exception:
        data = {}
    page_type = str((data.get("page") or {}).get("type") or "")
    continue_url = str(data.get("continue_url") or "").strip()
    if continue_url:
        try:
            session.get(
                continue_url,
                headers=navigate_headers(f"{AUTH_BASE}/email-verification"),
                timeout=30,
                allow_redirects=True,
            )
        except Exception:
            pass
    if page_type == "add_phone":
        raise RegistrationError(
            "OpenAI 要求手机验证 (add_phone)。换出口 IP/代理，或改用 platform 路径。"
        )
    return page_type


def create_account(session, device_id: str, name: str, birthdate: str) -> Optional[str]:
    try:
        session.get(
            f"{AUTH_BASE}/about-you",
            headers=navigate_headers(f"{AUTH_BASE}/email-verification"),
            timeout=30,
            allow_redirects=True,
        )
    except Exception:
        pass

    url = f"{AUTH_BASE}/api/accounts/create_account"
    headers = json_headers(f"{AUTH_BASE}/about-you", device_id)
    headers["openai-sentinel-token"] = build_sentinel_token(
        session, device_id, "oauth_create_account"
    )
    resp = session.post(
        url,
        headers=headers,
        data=json.dumps({"name": name, "birthdate": birthdate}),
        timeout=30,
        allow_redirects=False,
    )
    if resp.status_code not in (200, 302, 303):
        msg = _snip(resp)
        if "registration_disallowed" in msg:
            raise RegistrationError(
                "registration_disallowed：邮箱域名或 IP 被拒，换 OEP 池内账号 / 代理后重试。"
                f" raw={msg}"
            )
        raise RegistrationError(f"create_account HTTP {resp.status_code}: {msg}")

    continue_url = ""
    try:
        data = resp.json() if resp.text else {}
        if isinstance(data, dict):
            continue_url = str(data.get("continue_url") or "").strip()
    except Exception:
        pass
    if not continue_url and resp.status_code in (302, 303):
        continue_url = resp.headers.get("Location") or ""
    auth_code = _extract_code(continue_url) if continue_url else ""
    if continue_url:
        try:
            session.get(
                continue_url,
                headers=navigate_headers(f"{AUTH_BASE}/about-you"),
                timeout=30,
                allow_redirects=True,
            )
        except Exception:
            pass
    return auth_code or None


def exchange_oauth_token(session, code_verifier: str, auth_code: str) -> str:
    if not auth_code or not code_verifier:
        return ""
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": PLATFORM_BASE,
        "referer": f"{PLATFORM_BASE}/",
        "user-agent": USER_AGENT,
        "auth0-client": AUTH0_CLIENT,
    }
    resp = session.post(
        f"{AUTH_BASE}/api/accounts/oauth/token",
        headers=headers,
        json={
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": OAUTH_REDIRECT_URI,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        return ""
    try:
        data = resp.json() or {}
    except Exception:
        return ""
    return str(data.get("access_token") or "").strip()


def bootstrap_chatgpt(session) -> None:
    try:
        from .openai_headers import CHAT_BASE

        session.get(
            f"{CHAT_BASE}/",
            headers=navigate_headers(AUTH_BASE),
            timeout=30,
            allow_redirects=True,
        )
    except Exception:
        pass


def _extract_code(url: str) -> str:
    try:
        return str((parse_qs(urlparse(url).query).get("code") or [""])[0]).strip()
    except Exception:
        return ""
