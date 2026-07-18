# Layer: L1 积木层
# Contract: OAuth 授权链上的「Choose account」账号选择 DOM 步骤。
# Boundary: 只操作 Playwright page；不负责取号/短信。
# Why: 已登录 ChatGPT 会话进 OAuth 时常停在 choose account，不点无法继续。

from __future__ import annotations

import time
from typing import Any


def page_is_choose_account(page: Any) -> bool:
    url = (page.url or "").lower()
    if "choose-account" in url or "select-account" in url or "account-select" in url:
        return True
    body = _body(page).lower()
    title = ""
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    markers = (
        "choose an account",
        "choose account",
        "select an account",
        "select account",
        "选择账号",
        "选择一个账号",
        "选择账户",
    )
    if any(m in body for m in markers) or any(m in title for m in markers):
        return True
    return False


def click_choose_account(page: Any, *, preferred_email: str = "") -> bool:
    """在 Choose account 页点选账号。

    Contract:
    - 若 preferred_email 非空，优先点包含该邮箱的项
    - 否则点第一个可见账号项（通常只有刚注册的那一个）
    - 先等到含 @ 的可选项出现（最多 25s）
    Returns:
        True 表示点到了账号项。
    """
    preferred = (preferred_email or "").strip().lower()
    print(f"[*] choose account page url={page.url}")

    # 等账号列表渲染（路由到了但列表可能延迟）
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            # 有邮箱文本或 option 即可
            if preferred and page.locator(f"text={preferred_email}").count() > 0:
                break
            if page.locator('button:has-text("@"), [role="option"], div[role="button"]:has-text("@")').count() > 0:
                break
        except Exception:
            pass
        page.wait_for_timeout(350)

    # 1) 优先按邮箱文本点
    if preferred:
        for sel in (
            f'button:has-text("{preferred_email}")',
            f'[role="button"]:has-text("{preferred_email}")',
            f'div[role="button"]:has-text("{preferred_email}")',
            f'a:has-text("{preferred_email}")',
            f'label:has-text("{preferred_email}")',
            f'text={preferred_email}',
        ):
            if _click_visible(page, sel):
                print(f"[*] chose account by email={preferred_email}")
                page.wait_for_timeout(1200)
                return True

    # 2) 常见账号卡片 / 列表项
    for sel in (
        '[data-testid*="account" i]',
        'button[data-testid*="account" i]',
        'div[role="listbox"] [role="option"]',
        'ul[role="listbox"] li',
        'button:has-text("@")',
        'div[role="button"]:has-text("@")',
        'a:has-text("@")',
        # OpenAI auth 常见：邮箱在按钮内
        'button:has(div)',
    ):
        loc = page.locator(sel)
        try:
            n = loc.count()
            for i in range(min(n, 8)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                text = (el.inner_text() or "").strip()
                low = text.lower()
                # 跳过「使用其他账号 / Use another」类
                if any(
                    k in low
                    for k in (
                        "another",
                        "other account",
                        "use a different",
                        "其他账号",
                        "其他账户",
                        "换一个",
                    )
                ):
                    continue
                if preferred and preferred in low:
                    el.click(timeout=5000)
                    print(f"[*] chose account match text={text[:80]!r}")
                    page.wait_for_timeout(1200)
                    return True
                # 没有 preferred 时：含 @ 的优先
                if "@" in text or not preferred:
                    el.click(timeout=5000)
                    print(f"[*] chose account first visible text={text[:80]!r}")
                    page.wait_for_timeout(1200)
                    return True
        except Exception:
            continue

    # 3) 整页里找含 @ 的可点击节点
    try:
        candidates = page.locator("button, a, div[role='button'], [role='option']")
        n = candidates.count()
        for i in range(min(n, 20)):
            el = candidates.nth(i)
            if not el.is_visible():
                continue
            text = (el.inner_text() or "").strip()
            if "@" not in text:
                continue
            low = text.lower()
            if preferred and preferred not in low:
                continue
            el.click(timeout=5000)
            print(f"[*] chose account fallback text={text[:80]!r}")
            page.wait_for_timeout(1200)
            return True
    except Exception:
        pass

    print("[!] choose account: no clickable account item found")
    return False


def _click_visible(page: Any, selector: str) -> bool:
    loc = page.locator(selector)
    try:
        if loc.count() == 0:
            return False
        el = loc.first
        if not el.is_visible():
            return False
        el.click(timeout=5000)
        return True
    except Exception:
        return False


def _body(page: Any) -> str:
    try:
        return page.locator("body").inner_text(timeout=2000)[:2000]
    except Exception:
        return ""
