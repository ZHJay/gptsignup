# Layer: L1 积木层
# Contract: ChatGPT 网页注册 DOM：Login/Sign up → 邮箱 → OTP；资料页交给 browser_profile。
# Boundary: 只操作 Playwright page；邮箱领取/收码由 EmailService 负责。
# Why: VDS 上首页无邮箱框，须点 Log in / Sign up 弹出 modal 的 #email。

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
    """打开登录/注册入口（优先 Sign up / Log in 弹出邮箱 modal）。"""
    dismiss_cookie_banners(page)
    if _real_email_input(page) is not None:
        print("[*] 已在邮箱输入页，跳过 Login 按钮")
        return

    # Why: 注册优先 Sign up；没有再 Log in。首页误匹配会卡住。
    selectors = (
        'button:has-text("Sign up for free")',
        'button:has-text("Sign up")',
        'a:has-text("Sign up for free")',
        'a:has-text("Sign up")',
        'button:has-text("注册")',
        'a:has-text("注册")',
        'button:has-text("Log in")',
        'a:has-text("Log in")',
        'button:has-text("Log In")',
        'button:has-text("登录")',
        'a:has-text("登录")',
        '[data-testid="login-button"]',
        'button:has-text("Get started")',
        'a:has-text("Get started")',
    )
    if not click_first(page, selectors, timeout_ms=15_000):
        if _real_email_input(page) is not None:
            print("[*] 已在邮箱输入页，跳过 Login 按钮")
            return
        # 兜底：直开 auth 邮箱页
        print("[!] 首页无 Login 按钮，goto auth.openai.com create-account")
        try:
            page.goto(
                "https://auth.openai.com/create-account",
                wait_until="domcontentloaded",
                timeout=120_000,
            )
            page.wait_for_timeout(1500)
        except Exception as exc:
            raise BrowserSignupError(f"找不到 Log in 且直开 auth 失败: {exc}") from exc
        return

    page.wait_for_timeout(1200)
    print(f"[*] clicked login/signup url={page.url}")

    # 等 modal / 跳转出现真实邮箱框
    deadline = time.time() + 25
    while time.time() < deadline:
        if _real_email_input(page) is not None:
            print("[*] email modal/input ready")
            return
        if "auth.openai.com" in (page.url or ""):
            print(f"[*] navigated to auth url={page.url}")
            return
        page.wait_for_timeout(400)


def submit_email(page: Any, email: str) -> None:
    """输入邮箱并 Continue。"""
    # 若还没邮箱框，再尝试一次点 Login/Sign up
    if _real_email_input(page) is None:
        try:
            click_login(page)
        except BrowserSignupError:
            pass

    deadline = time.time() + 50
    el = None
    while time.time() < deadline:
        el = _real_email_input(page)
        if el is not None:
            try:
                el.wait_for(state="visible", timeout=5000)
                el.click(timeout=3000)
                el.fill("")
                el.fill(email)
                # 校验写进去了
                val = ""
                try:
                    val = el.input_value()
                except Exception:
                    val = email
                if email.split("@")[0][:4] in (val or ""):
                    break
                el.type(email, delay=20)
                break
            except Exception:
                page.wait_for_timeout(500)
                continue
        # modal 可能被挡：再点一次 Log in
        if int(time.time()) % 8 == 0:
            click_first(
                page,
                (
                    'button:has-text("Log in")',
                    'button:has-text("Sign up for free")',
                    'button:has-text("Sign up")',
                ),
                timeout_ms=1500,
            )
        page.wait_for_timeout(400)
    else:
        # 最后兜底直开 auth
        try:
            page.goto(
                "https://auth.openai.com/create-account",
                wait_until="domcontentloaded",
                timeout=120_000,
            )
            page.wait_for_timeout(1500)
            el = _real_email_input(page)
            if el is not None:
                el.fill(email)
            else:
                raise BrowserSignupError(
                    f"邮箱输入框未出现 url={page.url} body={body_snip(page)[:180]!r}"
                )
        except BrowserSignupError:
            raise
        except Exception as exc:
            raise BrowserSignupError(
                f"邮箱输入框未出现 url={page.url}: {exc}"
            ) from exc

    if not click_continue(page):
        # modal 里 Continue
        if not click_first(
            page,
            (
                'button:has-text("Continue")',
                'button[type="submit"]:has-text("Continue")',
                'button:has-text("继续")',
            ),
            timeout_ms=5000,
        ):
            try:
                _real_email_input(page).press("Enter")  # type: ignore[union-attr]
            except Exception as exc:
                raise BrowserSignupError(f"提交邮箱失败: {exc}") from exc
    page.wait_for_timeout(1200)
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
            # 排除首页假阳性
            try:
                if _otp_input(page).first.is_visible():
                    print(f"[*] OTP page ready url={page.url}")
                    return
            except Exception:
                pass
        if "email-verification" in url or "email_otp" in url:
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


def wait_profile_page(page: Any, timeout_s: float = 90) -> None:
    """等到 Full Name / Age 资料页（最好等到输入框已挂载）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_logged_in_chatgpt(page):
            print("[*] 已登录，跳过资料页")
            return
        if looks_like_profile_page(page):
            # about-you 路由到了仍可能表单未渲染，再等一小会有 name 输入
            try:
                if page.locator(
                    'input[name="name"], input[placeholder*="Full name" i], input[name="age"]'
                ).count() > 0:
                    print(f"[*] profile page ready url={page.url}")
                    return
            except Exception:
                pass
            # URL 已是 about-you：也算 ready，submit_profile 会再等输入框
            url = (page.url or "").lower()
            if "about-you" in url or "about_you" in url:
                print(f"[*] profile route ready (waiting inputs later) url={page.url}")
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


def _real_email_input(page: Any) -> Any | None:
    """返回可见、可编辑的邮箱框；排除 file/hidden。"""
    selectors = (
        'input#email',
        'input[type="email"]',
        'input[name="email"]',
        'input[autocomplete="email"]',
        'input[autocomplete="username"]',
        'input[placeholder="Email address"]',
        'input[placeholder*="Email" i]',
        'input[aria-label*="Email" i]',
    )
    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
            for i in range(min(n, 5)):
                el = loc.nth(i)
                typ = (el.get_attribute("type") or "").lower()
                if typ in {"hidden", "file", "checkbox", "radio", "submit", "button"}:
                    continue
                if not el.is_visible():
                    continue
                # 可编辑
                try:
                    if el.is_disabled():
                        continue
                except Exception:
                    pass
                return el
        except Exception:
            continue
    return None


def _otp_input(page: Any) -> Any:
    return page.locator(
        'input[autocomplete="one-time-code"], input[name*="code" i], '
        'input[aria-label*="code" i], input[placeholder*="code" i], input[maxlength="1"]'
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
