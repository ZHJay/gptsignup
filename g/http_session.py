# Layer: L1 积木层
# Contract: 创建带 TLS 指纹的 curl_cffi Session；探测可用 impersonate。
# Boundary: 只负责会话生命周期，不含注册业务。

from __future__ import annotations

import os
from typing import Optional

from curl_cffi import requests

from .openai_headers import AUTH_BASE, IMPERSONATE_CANDIDATES


def _proxy_dict(proxy: str) -> Optional[dict]:
    proxy = (proxy or "").strip()
    if not proxy:
        proxy = (os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "").strip()
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def pick_impersonate(proxy: str = "") -> str:
    """试探能访问 auth.openai.com 的 TLS 指纹。"""
    proxies = _proxy_dict(proxy)
    last_err = "no candidates"
    for imp in IMPERSONATE_CANDIDATES:
        try:
            with requests.Session(impersonate=imp, proxies=proxies) as s:
                res = s.get(f"{AUTH_BASE}/", timeout=20, allow_redirects=True)
                text = (res.text or "").lower()
                if res.status_code == 200 and "just a moment" not in text:
                    return imp
                last_err = f"{imp}->{res.status_code}"
        except Exception as exc:
            last_err = f"{imp}->{exc}"
    # 仍返回首选，让上层在请求时暴露错误
    print(f"[!] impersonate 探测未完全成功 ({last_err})，回退 chrome124")
    return "chrome124"


def create_session(proxy: str = "", impersonate: str = "") -> requests.Session:
    imp = impersonate or pick_impersonate(proxy)
    return requests.Session(impersonate=imp, proxies=_proxy_dict(proxy))


def is_cloudflare_challenge(resp) -> bool:
    if resp is None:
        return False
    try:
        status = int(getattr(resp, "status_code", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    if status not in (403, 503):
        return False
    text = str(getattr(resp, "text", "") or "").lower()
    return (
        "just a moment" in text
        or "attention required" in text
        or "cf-chl-" in text
        or "__cf_chl_" in text
    )
