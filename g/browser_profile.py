# Layer: L1 积木层
# Contract: about-you 页：Full name + Age → Finish creating account。
# Boundary: 仅 DOM；OTP/邮箱步骤在 browser_signup_steps。
# Why: VDS 上 about-you 常延迟渲染；须等待真实 name/age 输入再填。

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
            if page.locator(sel).count() > 0 and page.locator(sel).first.is_visible():
                return True
        except Exception:
            continue
    return False


def looks_like_profile_page(page: Any) -> bool:
    url = (page.url or "").lower()
    if "about-you" in url or "about_you" in url or "about_you" in url.replace("-", "_"):
        return True
    body = body_snip(page).lower()
    if "how old are you" in body:
        return True
    if "full name" in body and "age" in body:
        return True
    if "finish creating account" in body:
        return True
    try:
        if page.locator('input[name="name"], input[name="age"], input[placeholder*="Full name" i]').count() >= 1:
            return True
    except Exception:
        pass
    return False


def submit_profile(page: Any, *, full_name: str = "", age: int = 0) -> None:
    """Full Name → Tab → Age(成年) → Finish creating account。"""
    if is_logged_in_chatgpt(page):
        return

    full_name = (full_name or random_full_name()).strip()
    age = int(age or random.randint(22, 34))
    if age < 18:
        age = 18

    # Contract: 先等到 name 框真正可见，避免 about-you 路由到了但表单未挂载。
    name_el = _wait_name_input(page, timeout_s=40)
    if name_el is None:
        raise RuntimeError(
            "about-you: Full name 输入框未找到 "
            f"url={page.url} title={_safe_title(page)!r} body={body_snip(page)[:220]!r}"
        )

    _fill_text(name_el, full_name)
    print(f"[*] full_name={full_name}")

    # Why: 从 Full Name Tab 进 Age，兼容 React 受控输入。
    try:
        name_el.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(300)

    age_el = _focused_or_age_input(page)
    if age_el is None:
        age_el = _wait_age_input(page, timeout_s=10)
    if age_el is None:
        raise RuntimeError(
            "about-you: Age 输入框未找到 "
            f"url={page.url} body={body_snip(page)[:180]!r}"
        )
    _fill_text(age_el, str(age))
    print(f"[*] age={age} (tab-from-name)")

    try:
        age_el.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(400)

    clicked = click_first(
        page,
        (
            'button:has-text("Finish creating account")',
            'button:has-text("Finish creating")',
            'button:has-text("Finish")',
            'button:has-text("Create account")',
            'button:has-text("创建账户")',
            'button:has-text("完成")',
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Done")',
        ),
        timeout_ms=8000,
    )
    if not clicked:
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
        # 可能还要再点一次 finish
        click_first(
            page,
            (
                'button:has-text("Finish creating account")',
                'button[type="submit"]',
                'button:has-text("Continue")',
            ),
            timeout_ms=600,
        )
        page.wait_for_timeout(700)
    print(f"[!] still on profile url={page.url}")


def _wait_name_input(page: Any, *, timeout_s: float = 40) -> Any | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        el = _name_input(page)
        if el is not None:
            return el
        # SPA 渲染中
        try:
            page.wait_for_load_state("domcontentloaded", timeout=1000)
        except Exception:
            pass
        page.wait_for_timeout(400)
    return None


def _wait_age_input(page: Any, *, timeout_s: float = 10) -> Any | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        el = _age_input(page)
        if el is not None:
            return el
        page.wait_for_timeout(300)
    return None


def _name_input(page: Any) -> Any | None:
    selectors = (
        'input[name="name"]',
        'input[id*="name" i]',
        'input[placeholder="Full name"]',
        'input[placeholder*="Full name" i]',
        'input[placeholder*="Name" i]',
        'input[autocomplete="name"]',
        'input[aria-label*="Full name" i]',
        'input[aria-label*="Name" i]',
        'input[type="text"]',
    )
    # Playwright label API
    try:
        by_label = page.get_by_label("Full name", exact=False)
        if by_label.count() > 0 and by_label.first.is_visible():
            return by_label.first
    except Exception:
        pass
    try:
        by_ph = page.get_by_placeholder("Full name", exact=False)
        if by_ph.count() > 0 and by_ph.first.is_visible():
            return by_ph.first
    except Exception:
        pass

    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
            for i in range(min(n, 6)):
                el = loc.nth(i)
                typ = (el.get_attribute("type") or "text").lower()
                if typ in {"hidden", "file", "checkbox", "radio", "email", "password", "number"}:
                    # number 留给 age；name 一般是 text
                    if typ != "text" and "name" not in sel:
                        continue
                    if typ in {"hidden", "file", "checkbox", "radio", "email", "password"}:
                        continue
                if not el.is_visible():
                    continue
                # 跳过明显不是名字的框
                name = (el.get_attribute("name") or "").lower()
                ph = (el.get_attribute("placeholder") or "").lower()
                aria = (el.get_attribute("aria-label") or "").lower()
                if any(k in name or k in ph or k in aria for k in ("email", "phone", "code", "search")):
                    continue
                if "age" in name or ph == "age":
                    continue
                return el
        except Exception:
            continue
    return None


def _age_input(page: Any) -> Any | None:
    try:
        by_label = page.get_by_label("Age", exact=False)
        if by_label.count() > 0 and by_label.first.is_visible():
            return by_label.first
    except Exception:
        pass
    try:
        by_ph = page.get_by_placeholder("Age", exact=False)
        if by_ph.count() > 0 and by_ph.first.is_visible():
            return by_ph.first
    except Exception:
        pass
    for sel in (
        'input[name="age"]',
        'input[id*="age" i]',
        'input[placeholder="Age"]',
        'input[placeholder*="Age" i]',
        'input[aria-label*="Age" i]',
        'input[type="number"]',
    ):
        loc = page.locator(sel)
        try:
            n = loc.count()
            for i in range(min(n, 4)):
                el = loc.nth(i)
                typ = (el.get_attribute("type") or "").lower()
                if typ == "hidden":
                    continue
                if el.is_visible():
                    return el
        except Exception:
            continue
    return None


def _focused_or_age_input(page: Any) -> Any | None:
    try:
        focused = page.evaluate_handle("() => document.activeElement")
        tag = focused.evaluate("el => el && el.tagName")
        name = focused.evaluate("el => (el && el.name) || ''")
        typ = focused.evaluate("el => (el && el.type) || ''")
        ph = focused.evaluate("el => (el && el.placeholder) || ''")
        if tag == "INPUT" and (
            name == "age" or typ == "number" or "age" in str(ph).lower()
        ):
            return focused.as_element()
    except Exception:
        pass
    return _age_input(page)


def _fill_text(el: Any, value: str) -> None:
    el.click(timeout=5000)
    try:
        el.fill("")
    except Exception:
        pass
    try:
        el.fill(value)
    except Exception:
        el.type(value, delay=30)
    # React 受控：再敲一次确保
    try:
        cur = el.input_value()
        if value and value not in (cur or ""):
            el.fill("")
            el.type(value, delay=25)
    except Exception:
        pass


def _safe_title(page: Any) -> str:
    try:
        return page.title() or ""
    except Exception:
        return ""


def random_full_name() -> str:
    first = random.choice(
        ["James", "Robert", "John", "Michael", "Emma", "Olivia", "Liam", "Sophia", "Noah", "Ava"]
    )
    last = random.choice(
        ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
    )
    return f"{first} {last}"
