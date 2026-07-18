# Layer: L1 积木层
# Contract: Playwright DOM 通用点击/填充/正文摘取。
# Boundary: 无业务语义；被 signup steps 复用。

from __future__ import annotations

from typing import Any


def click_first(page: Any, selectors: tuple[str, ...], *, timeout_ms: int = 3000) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() == 0:
                continue
            el = loc.first
            if not el.is_visible():
                continue
            el.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def fill_first(page: Any, selectors: tuple[str, ...], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
            if n == 0:
                continue
            for i in range(min(n, 3)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                el.click(timeout=2000)
                el.fill("")
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def body_snip(page: Any, limit: int = 1200) -> str:
    try:
        return page.locator("body").inner_text(timeout=2000)[:limit]
    except Exception:
        return ""


def click_continue(page: Any) -> bool:
    return click_first(
        page,
        (
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("继续")',
            'button:has-text("Next")',
            'button:has-text("Verify")',
            'button:has-text("Submit")',
            '[data-testid*="continue" i]',
        ),
        timeout_ms=5000,
    )


def dismiss_cookie_banners(page: Any) -> None:
    click_first(
        page,
        (
            'button:has-text("Accept all")',
            'button:has-text("Accept")',
            'button:has-text("同意")',
            'button:has-text("Reject non-essential")',
        ),
        timeout_ms=800,
    )
