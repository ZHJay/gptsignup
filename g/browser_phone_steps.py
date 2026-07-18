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
    if _otp_input(page).count() > 0:
        return True
    body = _body(page).lower()
    return "verification code" in body or "enter the code" in body or "验证码" in body


def submit_phone_national(page: Any, national_number: str) -> None:
    """输入不带国家码的电话号并 Continue。"""
    digits = re.sub(r"\D", "", national_number or "")
    if len(digits) < 7:
        raise BrowserPhoneError(f"invalid national number: {national_number!r}")

    # 优先 tel / phone 输入；避开已只读的国家码框
    filled = False
    for sel in (
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[autocomplete="tel-national"]',
        'input[autocomplete="tel"]',
        'input[placeholder*="phone" i]',
        'input[inputmode="tel"]',
        'input[inputmode="numeric"]',
    ):
        loc = page.locator(sel)
        try:
            n = loc.count()
            if n == 0:
                continue
            for i in range(n):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                # 跳过极短国家码框
                try:
                    ml = el.get_attribute("maxlength")
                    if ml and ml.isdigit() and int(ml) <= 4:
                        continue
                except Exception:
                    pass
                el.click(timeout=3000)
                el.fill("")
                el.type(digits, delay=40)
                filled = True
                break
        except Exception:
            continue
        if filled:
            break
    if not filled:
        raise BrowserPhoneError(f"phone input not found url={page.url}")

    print(f"[*] phone national filled len={len(digits)}")
    if not _click_continue(page):
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
    page.wait_for_timeout(1200)


def submit_sms_code(page: Any, code: str) -> None:
    """仅提交调用方传入的验证码；禁止空码/短码。"""
    code = re.sub(r"\D", "", str(code or ""))
    if len(code) < 4:
        raise BrowserPhoneError(
            f"refuse to submit invalid/empty sms code: {code!r}"
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
