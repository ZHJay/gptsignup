# Layer: L1 积木层
# Contract: OpenAI 授权页手机号步骤：填本地号（无区号）→ Continue → 填 SMS 码。
# Boundary: 只操作 Playwright page；取号/收码由 PhoneService。
# Why: OAuth 授权链常触发 add-phone；页面区号已自填，只能输 national number。

from __future__ import annotations

import re
import time
from typing import Any


class BrowserPhoneError(RuntimeError):
    """手机验证 DOM 步骤失败。"""


def page_needs_phone(page: Any) -> bool:
    url = (page.url or "").lower()
    if "add-phone" in url or "phone-verification" in url or "phone_otp" in url:
        return True
    body = _body(page).lower()
    return (
        "phone number" in body
        or "verify your phone" in body
        or "add a phone" in body
        or "手机号" in body
    )


def page_has_otp(page: Any) -> bool:
    """必须有可见 OTP 输入，避免仅 body 文案误判。"""
    loc = _otp_input(page)
    try:
        n = loc.count()
        for i in range(min(n, 8)):
            el = loc.nth(i)
            if el.is_visible():
                return True
    except Exception:
        pass
    # URL 强信号
    url = (page.url or "").lower()
    if "email-verification" in url or "phone-otp" in url or "code" in url and "auth.openai.com" in url:
        # 仍要求最终有输入框；这里只作弱提示
        pass
    return False


def submit_phone_national(page: Any, national_number: str) -> None:
    """输入不带国家码的电话号并 Continue。"""
    from .browser_wait import wait_visible

    digits = re.sub(r"\D", "", national_number or "")
    if len(digits) < 7:
        raise BrowserPhoneError(f"invalid national number: {national_number!r}")

    # 等电话输入真正出现
    phone_el = wait_visible(
        page,
        (
            'input[type="tel"]',
            'input[name*="phone" i]',
            'input[autocomplete="tel-national"]',
            'input[autocomplete="tel"]',
            'input[placeholder*="phone" i]',
            'input[inputmode="tel"]',
        ),
        timeout_s=30,
    )
    if phone_el is None:
        raise BrowserPhoneError(
            f"phone input not found url={page.url} body={_body(page)[:160]!r}"
        )

    # 跳过极短国家码框：若命中则找下一个
    try:
        ml = phone_el.get_attribute("maxlength")
        if ml and ml.isdigit() and int(ml) <= 4:
            phone_el = wait_visible(
                page,
                (
                    'input[type="tel"]',
                    'input[autocomplete="tel-national"]',
                    'input[placeholder*="phone" i]',
                ),
                timeout_s=5,
            )
    except Exception:
        pass
    if phone_el is None:
        raise BrowserPhoneError(f"phone input not found after skip country box url={page.url}")

    phone_el.click(timeout=3000)
    phone_el.fill("")
    phone_el.type(digits, delay=40)
    print(f"[*] phone national filled len={len(digits)}")
    if not _click_continue(page):
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
    page.wait_for_timeout(1200)


def submit_sms_code(page: Any, code: str) -> None:
    """仅提交调用方传入的验证码；禁止空码/短码。"""
    from .browser_wait import wait_visible

    code = re.sub(r"\D", "", str(code or ""))
    if len(code) < 4:
        raise BrowserPhoneError(
            f"refuse to submit invalid/empty sms code: {code!r}"
        )

    # 等 OTP 输入可见
    el0 = wait_visible(
        page,
        (
            'input[autocomplete="one-time-code"]',
            'input[name*="code" i]',
            'input[aria-label*="code" i]',
            'input[placeholder*="code" i]',
            'input[maxlength="1"]',
            'input[inputmode="numeric"]',
        ),
        timeout_s=30,
    )
    if el0 is None:
        raise BrowserPhoneError(
            f"sms code input not found url={page.url} body={_body(page)[:160]!r}"
        )

    loc = _otp_input(page)
    if loc.count() == 0:
        loc = page.locator(
            'input[type="text"], input[type="tel"], input[inputmode="numeric"]'
        )
    if loc.count() == 0:
        raise BrowserPhoneError("sms code input not found")

    if loc.count() >= 4 and loc.count() <= 8:
        for i, ch in enumerate(code[: loc.count()]):
            try:
                box = loc.nth(i)
                box.wait_for(state="visible", timeout=5000)
                box.click(timeout=2000)
                box.fill(ch)
            except Exception:
                pass
    else:
        el = loc.first
        el.click(timeout=3000)
        el.fill("")
        el.type(code, delay=40)

    if not _click_continue(page):
        try:
            loc.first.press("Enter")
        except Exception:
            pass
    page.wait_for_timeout(1500)
    print(f"[*] sms code submitted len={len(code)} (from Tiger SMS only)")


def wait_phone_or_done(page: Any, *, timeout_s: float = 90) -> str:
    """返回 phone | otp | done | other。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = (page.url or "").lower()
        if page_has_otp(page):
            return "otp"
        if page_needs_phone(page):
            return "phone"
        # OAuth 回调 / 完成
        if "code=" in url or "localhost" in url or "127.0.0.1" in url:
            return "done"
        if "chatgpt.com" in url and "auth.openai.com" not in url:
            return "done"
        if "error" in url and "access_denied" in url:
            return "error"
        page.wait_for_timeout(700)
    return "other"


def _otp_input(page: Any) -> Any:
    return page.locator(
        'input[autocomplete="one-time-code"], input[name*="code" i], '
        'input[aria-label*="code" i], input[placeholder*="code" i], input[maxlength="1"]'
    )


def _click_continue(page: Any) -> bool:
    for sel in (
        'button[type="submit"]',
        'button:has-text("Continue")',
        'button:has-text("继续")',
        'button:has-text("Verify")',
        'button:has-text("Send")',
        'button:has-text("Next")',
        'button:has-text("Resend")',
    ):
        loc = page.locator(sel)
        try:
            if loc.count() > 0 and loc.first.is_visible() and loc.first.is_enabled():
                # 跳过 Resend 优先 Continue
                text = (loc.first.inner_text() or "").lower()
                if "resend" in text:
                    continue
                loc.first.click(timeout=4000)
                return True
        except Exception:
            continue
    # 再点 Continue 含 resend 的列表
    for sel in ('button:has-text("Continue")', 'button[type="submit"]'):
        loc = page.locator(sel)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=4000)
                return True
        except Exception:
            continue
    return False


def _body(page: Any) -> str:
    try:
        return page.locator("body").inner_text(timeout=2000)[:1500]
    except Exception:
        return ""
