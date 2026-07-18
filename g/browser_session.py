# Layer: L1 积木层
# Contract: Playwright 启停、打开页面、等 CF 消失、页内 fetch JSON。
# Boundary: 仅浏览器生命周期与基础导航；不负责邮箱/OTP/业务表单。
# Why: 纯协议注册易 400/429；真实浏览器走 chatgpt.com Login 链路更稳。
# Risk: headless 仍可能被 CF 拦；机房建议有头 + xvfb，或干净代理。

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore


def _require_playwright() -> None:
    if sync_playwright is None:
        raise RuntimeError(
            "未安装 playwright。请执行: pip install playwright && playwright install chromium"
        )


def _is_cf_challenge(title: str, body: str) -> bool:
    t = (title or "").lower()
    b = (body or "").lower()
    if not t and len(b) < 40:
        # 标题还空、正文几乎无内容：更像挑战/加载中，不能当通过
        return True
    return (
        "just a moment" in t
        or "just a moment" in b
        or "attention required" in t
        or "attention required" in b
        or "enable javascript and cookies to continue" in b
        or "checking your browser" in t
        or "checking your browser" in b
        or "cf-chl-" in b
        or "cf-browser-verification" in b
        or "challenge-platform" in b
    )


class BrowserSession:
    """有头/无头 Chromium：打开 ChatGPT 注册链路。"""

    def __init__(
        self,
        *,
        proxy: str = "",
        headless: bool | None = None,
        channel: str = "",
        timeout_ms: int = 120_000,
    ) -> None:
        _require_playwright()
        self.proxy = (proxy or os.getenv("PROXY") or "").strip()
        if headless is None:
            env = (os.getenv("BROWSER_HEADLESS") or "0").strip().lower()
            headless = env in {"1", "true", "yes", "on"}
        self.headless = bool(headless)
        self.channel = (channel or os.getenv("BROWSER_CHANNEL") or "chrome").strip()
        self.timeout_ms = int(os.getenv("BROWSER_TIMEOUT_MS") or timeout_ms)
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self.user_agent = ""

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def start(self) -> None:
        if self._page is not None:
            return
        self._pw = sync_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
            ],
        }
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        browser = None
        last_err: Exception | None = None
        for channel in (self.channel, "chrome", "chromium", ""):
            try:
                kw = dict(launch_kwargs)
                if channel and channel not in {"chromium", ""}:
                    kw["channel"] = channel
                browser = self._pw.chromium.launch(**kw)
                print(
                    f"[*] browser launched channel={channel or 'chromium'} "
                    f"headless={self.headless}"
                )
                break
            except Exception as exc:
                last_err = exc
                continue
        if browser is None:
            raise RuntimeError(f"无法启动浏览器: {last_err}")

        self._browser = browser
        self._context = browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(30_000)
        self.user_agent = self._page.evaluate("() => navigator.userAgent") or ""

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._page = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    @property
    def page(self) -> Any:
        if self._page is None:
            raise RuntimeError("browser not started")
        return self._page

    def new_page(self) -> Any:
        """同 context 新开页，共享 cookie（ChatGPT 登录态）。"""
        if self._context is None:
            raise RuntimeError("browser not started")
        return self._context.new_page()

    def open(self, url: str, *, wait_cf: bool = True) -> str:
        """打开 URL；可选等待 Cloudflare 挑战结束。返回最终 URL。

        Why: VDS 机房出口常 403/卡 CF；goto 用更松的 wait + 重试，并给出可操作错误。
        """
        self.start()
        page = self.page
        print(f"[*] browser open: {url}")
        last_err: Exception | None = None
        # commit 最快；domcontentloaded 在 CF/慢网下易拖满 timeout
        strategies = (
            ("commit", min(self.timeout_ms, 45_000)),
            ("domcontentloaded", self.timeout_ms),
            ("load", self.timeout_ms),
        )
        for attempt in range(1, 4):
            for wait_until, timeout in strategies:
                try:
                    page.goto(url, wait_until=wait_until, timeout=timeout)
                    last_err = None
                    break
                except Exception as exc:
                    last_err = exc
                    print(
                        f"[!] goto fail attempt={attempt} wait_until={wait_until}: "
                        f"{str(exc)[:120]}"
                    )
                    page.wait_for_timeout(800)
            else:
                # 本轮 strategies 全失败
                if attempt < 3:
                    page.wait_for_timeout(1500 * attempt)
                continue
            break
        if last_err is not None:
            proxy_hint = (
                "已配置 PROXY"
                if self.proxy
                else "未配置 PROXY——VDS 机房 IP 访问 chatgpt.com 常 403/超时，请在 .env 设置 PROXY="
            )
            raise RuntimeError(
                f"打开 {url} 失败（3 次重试）: {last_err}; {proxy_hint}"
            ) from last_err

        # 给 SPA/CF 一点时间出 title
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:
            pass
        if wait_cf:
            self.wait_cf_clear()
        return str(page.url or "")

    def wait_cf_clear(self) -> None:
        page = self.page
        deadline = time.time() + self.timeout_ms / 1000.0
        last_title = ""
        clear_hits = 0
        while time.time() < deadline:
            try:
                last_title = page.title() or ""
                body_snip = page.locator("body").inner_text(timeout=2000)[:800]
            except Exception:
                last_title = ""
                body_snip = ""
            if not _is_cf_challenge(last_title, body_snip):
                clear_hits += 1
                # Why: 连续两次非挑战，避免 title 瞬时空白误判为通过。
                if clear_hits >= 2:
                    print(f"[*] CF clear title={last_title!r}")
                    page.wait_for_timeout(500)
                    return
            else:
                clear_hits = 0
                print(f"[*] 等待 Cloudflare... title={last_title!r}")
            page.wait_for_timeout(1500)
        raise RuntimeError(f"Cloudflare 超时 title={last_title!r}")

    def page_fetch_json(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        body: Any = None,
    ) -> tuple[int, Any, str]:
        """页内 fetch，带上浏览器 cookie。返回 (status, json|None, raw)."""
        page = self.page
        hdrs = dict(headers or {})
        for k in list(hdrs.keys()):
            if k.lower() == "cookie":
                hdrs.pop(k)
        payload = {
            "url": url,
            "method": (method or "GET").upper(),
            "headers": hdrs,
            "body": body if isinstance(body, str) or body is None else json.dumps(body),
        }
        result = page.evaluate(
            """async ({url, method, headers, body}) => {
                const init = {method, headers: headers || {}, credentials: 'include'};
                if (body !== null && body !== undefined && method !== 'GET' && method !== 'HEAD') {
                    init.body = body;
                }
                const resp = await fetch(url, init);
                const text = await resp.text();
                return {status: resp.status, text};
            }""",
            payload,
        )
        status = int((result or {}).get("status") or 0)
        text = str((result or {}).get("text") or "")
        data: Any = None
        try:
            data = json.loads(text) if text else None
        except Exception:
            data = None
        return status, data, text
