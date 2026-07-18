# Layer: L1 积木层
# Contract: about-you 页：Full name + Age → Finish creating account。
# Boundary: 仅 DOM；OTP/邮箱步骤在 browser_signup_steps。
# Why: 实测表单是 name/age 两个可见输入 + 文案按钮，不是旧 birthday 下拉。

from __future__ import annotations

import random
import time
from typing import Any

from .browser_dom import body_snip, click_first


def is_logged_in_chatgpt(page: Any) -> bool:
    url = (page.url or "").lower()
    if "auth.openai.com" in url or "auth0" in url:
        return False
    if "chatgpt.com" not in url and "chat.openai.com" not in url:
        return False
    for sel in (
        "#prompt-textarea",
        'textarea[data-id="root"]',
        'div[contenteditable="true"]',
        'button[data-testid="send-button"]',
        'nav[aria-label*="Chat history" i]',
    ):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def looks_like_profile_page(page: Any) -> bool:
    url = (page.url or "").lower()
    if "about-you" in url or "about_you" in url:
        return True
    body = body_snip(page).lower()
    if "how old are you" in body or "full name" in body and "age" in body:
        return True
    try:
        return page.locator('input[name="name"], input[name="age"]').count() >= 1
    except Exception:
        return False


def submit_profile(page: Any, *, full_name: str = "", age: int = 0) -> None:
    """Full Name → Tab → Age(成年) → Finish creating account。"""
    if is_logged_in_chatgpt(page):
        return

    full_name = (full_name or random_full_name()).strip()
    # Contract: Age 必须成年；默认 22–34，禁止 <18。
    age = int(age or random.randint(22, 34))
    if age < 18:
        age = 18

    name_el = _name_input(page)
    if name_el is None:
        raise RuntimeError("about-you: Full name 输入框未找到")
    name_el.click(timeout=5000)
    name_el.fill("")
    name_el.type(full_name, delay=30)
    print(f"[*] full_name={full_name}")

    # Why: 实测需从 Full Name Tab 进 Age，直接点/fill age 有时不触发校验。
    name_el.press("Tab")
    page.wait_for_timeout(200)

    age_el = _focused_or_age_input(page)
    if age_el is None:
        raise RuntimeError("about-you: Age 输入框未找到")
    try:
        age_el.fill("")
    except Exception:
        pass
    age_el.type(str(age), delay=40)
    print(f"[*] age={age} (tab-from-name)")

    # 失焦触发 React change
    try:
        age_el.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(400)

    clicked = click_first(
        page,
        (
            'button:has-text("Finish creating account")',
            'button:has-text("Finish")',
            'button:has-text("Create account")',
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Done")',
        ),
        timeout_ms=8000,
    )
    if not clicked:
        # 回车提交兜底
        try:
            age_el.press("Enter")
            clicked = True
        except Exception:
            print("[!] profile submit button not clicked")
    if clicked:
        print(f"[*] profile submit clicked url={page.url}")

    deadline = time.time() + 45
    while time.time() < deadline:
        url = (page.url or "").lower()
        if "about-you" not in url and "about_you" not in url:
            print(f"[*] left about-you url={page.url}")
            return
        if is_logged_in_chatgpt(page):
            return
        page.wait_for_timeout(700)
    print(f"[!] still on profile url={page.url}")


def _name_input(page: Any) -> Any | None:
    for sel in (
        'input[name="name"]',
        'input[placeholder="Full name"]',
        'input[placeholder*="Full name" i]',
        'input[autocomplete="name"]',
    ):
        loc = page.locator(sel)
        try:
            if loc.count() == 0:
                continue
            el = loc.first
            typ = (el.get_attribute("type") or "").lower()
            if typ == "hidden":
                continue
            el.wait_for(state="visible", timeout=5000)
            return el
        except Exception:
            continue
    return None


def _focused_or_age_input(page: Any) -> Any | None:
    # Tab 后优先当前焦点；否则回退 name=age
    try:
        focused = page.evaluate_handle("() => document.activeElement")
        tag = focused.evaluate("el => el && el.tagName")
        name = focused.evaluate("el => (el && el.name) || ''")
        typ = focused.evaluate("el => (el && el.type) || ''")
        if tag == "INPUT" and (name == "age" or typ == "number"):
            return focused.as_element()
    except Exception:
        pass
    for sel in (
        'input[name="age"]',
        'input[placeholder="Age"]',
        'input[placeholder*="Age" i]',
        'input[type="number"]',
    ):
        loc = page.locator(sel)
        try:
            if loc.count() == 0:
                continue
            el = loc.first
            typ = (el.get_attribute("type") or "").lower()
            if typ == "hidden":
                continue
            if el.is_visible():
                el.click(timeout=2000)
                return el
        except Exception:
            continue
    return None


def random_full_name() -> str:
    first = random.choice(
        ["James", "Robert", "John", "Michael", "Emma", "Olivia", "Liam", "Sophia", "Noah", "Ava"]
    )
    last = random.choice(
        ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
    )
    return f"{first} {last}"
