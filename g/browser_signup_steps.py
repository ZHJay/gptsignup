# Layer: L1 积木层
# Contract: ChatGPT 网页注册 DOM：Login → 邮箱 → OTP；资料页交给 browser_profile。
# Boundary: 只操作 Playwright page；邮箱领取/收码由 EmailService 负责。
# Why: 用户确认链路为 chatgpt.com 点 Login 后的无密码 OTP 注册流。

from __future__ import annotations

import re
import time
from typing import Any

from .browser_dom import (
    body_snip,
    click_continue,
    click_first,
    dismiss_cookie_banners,
)
from .browser_profile import (
    is_logged_in_chatgpt,
    looks_like_profile_page,
    submit_profile,
)

__all__ = [
    "BrowserSignupError",
    "click_login",
    "submit_email",
    "wait_otp_page",
    "submit_otp",
    "wait_profile_page",
    "submit_profile",
    "wait_registered",
]


class BrowserSignupError(RuntimeError):
    """浏览器注册步骤失败。"""


def click_login(page: Any) -> None:
    """在 chatgpt.com 首页点 Log in。"""
    dismiss_cookie_banners(page)
    # 已在可见邮箱框则跳过
    if _visible_email_input(page):
        print("[*] 已在邮箱输入页，跳过 Login 按钮")
        return
    selectors = (
        'button:has-text("Log in")',
        'a:has-text("Log in")',
        'button:has-text("Log In")',
        'a:has-text("Log In")',
        'button:has-text("登录")',
        'a:has-text("登录")',
        '[data-testid="login-button"]',
        'button:has-text("Sign up")',
        'a:has-text("Sign up")',
        'button:has-text("Get started")',
        'a:has-text("Get started")',
    )
    if not click_first(page, selectors, timeout_ms=12_000):
        if _visible_email_input(page):
            print("[*] 已在邮箱输入页，跳过 Login 按钮")
            return
        raise BrowserSignupError("找不到 Log in 按钮")
    page.wait_for_timeout(800)
    print(f"[*] clicked login url={page.url}")


def _visible_email_input(page: Any) -> bool:
    loc = _email_input(page)
    try:
        if loc.count() == 0:
            return False
        return bool(loc.first.is_visible())
    except Exception:
        return False


def submit_email(page: Any, email: str) -> None:
    """输入邮箱并 Continue。"""
    deadline = time.time() + 45
    while time.time() < deadline:
        loc = _email_input(page)
        if loc.count() > 0:
            try:
                el = loc.first
                el.wait_for(state="visible", timeout=5000)
                el.click(timeout=3000)
                el.fill("")
                el.fill(email)
                break
            except Exception:
                page.wait_for_timeout(500)
                continue
        page.wait_for_timeout(400)
    else:
        raise BrowserSignupError(f"邮箱输入框未出现 url={page.url}")

    if not click_continue(page):
        try:
            _email_input(page).first.press("Enter")
        except Exception as exc:
            raise BrowserSignupError(f"提交邮箱失败: {exc}") from exc
    page.wait_for_timeout(1000)
    print(f"[*] email submitted url={page.url}")


def wait_otp_page(page: Any, timeout_s: float = 60) -> None:
    """等到验证码输入页。若出现密码登录页则判脏号。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = (page.url or "").lower()
        title = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        if _looks_like_password_page(page, url, title):
            raise BrowserSignupError(
                f"email not signup-ready: page=login_password url={page.url}"
            )
        if _otp_input(page).count() > 0:
            print(f"[*] OTP page ready url={page.url}")
            return
        page.wait_for_timeout(500)
    raise BrowserSignupError(f"OTP 页超时 url={page.url}")


def submit_otp(page: Any, code: str) -> None:
    """填入邮箱验证码并 Continue。"""
    code = re.sub(r"\D", "", str(code or ""))
    if len(code) < 4:
        raise BrowserSignupError(f"invalid otp: {code!r}")

    loc = _otp_input(page)
    if loc.count() == 0:
        raise BrowserSignupError("找不到验证码输入框")

    if loc.count() >= 4 and loc.count() <= 8:
        for i, ch in enumerate(code[: loc.count()]):
            try:
                box = loc.nth(i)
                box.click(timeout=2000)
                box.fill(ch)
            except Exception:
                pass
    else:
        el = loc.first
        el.click(timeout=3000)
        el.fill("")
        el.fill(code)

    if not click_continue(page):
        try:
            loc.first.press("Enter")
        except Exception:
            pass
    page.wait_for_timeout(1200)
    print(f"[*] OTP submitted url={page.url}")


def wait_profile_page(page: Any, timeout_s: float = 60) -> None:
    """等到 Full Name / Age（或 birthday）资料页。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_logged_in_chatgpt(page):
            print("[*] 已登录，跳过资料页")
            return
        if looks_like_profile_page(page):
            print(f"[*] profile page ready url={page.url}")
            return
        click_first(
            page,
            (
                'button:has-text("Accept")',
                'button:has-text("Agree")',
                'button:has-text("I agree")',
                'button:has-text("Continue")',
                'button:has-text("继续")',
            ),
            timeout_ms=800,
        )
        page.wait_for_timeout(500)
    raise BrowserSignupError(f"资料页超时 url={page.url}")


def wait_registered(page: Any, timeout_s: float = 90) -> None:
    """等到进入 ChatGPT 主站会话。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_logged_in_chatgpt(page):
            print(f"[*] registered url={page.url}")
            return
        click_first(
            page,
            (
                'button:has-text("Okay")',
                'button:has-text("Got it")',
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'button:has-text("Skip")',
                'button[aria-label="Close"]',
            ),
            timeout_ms=600,
        )
        page.wait_for_timeout(700)
    print(f"[!] 未确认主站 UI，继续取 session url={page.url}")


def _email_input(page: Any) -> Any:
    return page.locator(
        'input[type="email"], input[name*="email" i], input[autocomplete="username"], '
        'input[autocomplete="email"], input[placeholder*="email" i]'
    )


def _otp_input(page: Any) -> Any:
    return page.locator(
        'input[autocomplete="one-time-code"], input[name*="code" i], '
        'input[inputmode="numeric"], input[aria-label*="code" i], '
        'input[placeholder*="code" i], input[maxlength="1"]'
    )


def _looks_like_password_page(page: Any, url: str, title: str) -> bool:
    if "password" in url or "create a password" in title or "enter your password" in title:
        return True
    try:
        if page.locator('input[type="password"]').count() > 0:
            return True
    except Exception:
        pass
    body = body_snip(page).lower()
    return "enter your password" in body or "create a password" in body
