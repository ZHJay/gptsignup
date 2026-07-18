# Layer: L1 积木层
# Contract: Sub2API 管理端：登录 → ESC 清弹窗 → 账号管理 → 添加 OpenAI → 手动授权。
# Boundary: 只操作 Playwright page；OAuth 授权页由调用方在同 context 另开页完成。
# Why: 用户要求等面板完全加载后 ESC 清弹窗，再经侧栏进入账号管理，勿直跳 URL 漏弹窗。

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import parse_qs, urlparse


class AdminImportError(RuntimeError):
    """管理端导入失败。"""


def ensure_admin_login(page: Any, *, base_url: str, email: str, password: str) -> None:
    """登录管理端，等完全加载后 ESC 清弹窗（不进入账号页）。"""
    base = base_url.rstrip("/")
    page.goto(f"{base}/login", wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(800)

    if _has_login_form(page):
        print("[*] admin login required")
        email_el = page.locator('#email, input[type="email"], input[name="email"]').first
        pass_el = page.locator('#password, input[type="password"], input[name="password"]').first
        email_el.wait_for(state="visible", timeout=20000)
        email_el.fill(email)
        pass_el.fill(password)
        clicked = False
        for sel in (
            'button[type="submit"]',
            'button:has-text("登录")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
        ):
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                clicked = True
                break
        if not clicked:
            pass_el.press("Enter")

    # 等登录完成：离开 /login，侧栏/主内容出现
    _wait_admin_shell_ready(page, timeout_s=60)
    if "/login" in (page.url or ""):
        raise AdminImportError("admin login failed")

    # Why: 登录后常有 onboarding/合规/公告弹窗，需完全加载后再 ESC。
    _wait_page_fully_loaded(page)
    _dismiss_popups_with_esc(page)
    print(f"[*] admin shell ready url={page.url}")


def open_accounts_and_create_openai(page: Any, account_name: str) -> None:
    """侧栏「账号管理」→「添加账号」→ 名称/OpenAI/下一步。"""
    _wait_page_fully_loaded(page)
    _dismiss_popups_with_esc(page)

    if not _goto_accounts_via_nav(page):
        raise AdminImportError("找不到侧栏「账号管理」")
    _wait_page_fully_loaded(page)
    _dismiss_popups_with_esc(page)
    print(f"[*] accounts page url={page.url}")

    open_create_openai_account(page, account_name)


def open_create_openai_account(page: Any, account_name: str) -> None:
    """点添加账号 → 填名称 → OpenAI → 下一步。"""
    from .browser_wait import wait_visible

    _dismiss_popups_with_esc(page)
    add_btn = wait_visible(
        page,
        (
            'button:has-text("添加账号")',
            'button:has-text("Create Account")',
            'button:has-text("Add Account")',
            'button:has-text("新建账号")',
        ),
        timeout_s=25,
        require_enabled=True,
    )
    if add_btn is None:
        raise AdminImportError("找不到「添加账号」按钮")
    add_btn.click(timeout=8000)
    page.wait_for_timeout(800)

    name_input = wait_visible(
        page,
        (
            '[data-tour="account-form-name"]',
            'input[placeholder*="账户"]',
            'input[placeholder*="Account"]',
            'input[placeholder*="名称"]',
            'input[placeholder*="name" i]',
        ),
        timeout_s=25,
    )
    if name_input is None:
        raise AdminImportError("添加账号弹窗：账户名称输入框未出现")
    name_input.click(timeout=3000)
    name_input.fill("")
    name_input.fill(account_name)
    print(f"[*] account name={account_name}")

    platform = page.locator('[data-tour="account-form-platform"]')
    if platform.count() > 0:
        btn = platform.locator('button:has-text("OpenAI")')
        if btn.count() > 0:
            btn.first.click()
        else:
            buttons = platform.locator("button")
            if buttons.count() >= 2:
                buttons.nth(1).click()
    else:
        _click_any(page, ('button:has-text("OpenAI")',))
    page.wait_for_timeout(400)

    type_box = page.locator('[data-tour="account-form-type"]')
    if type_box.count() > 0:
        oauth_btn = type_box.locator('button:has-text("OAuth")')
        if oauth_btn.count() > 0:
            oauth_btn.first.click()
    page.wait_for_timeout(300)

    next_btn = wait_visible(
        page,
        (
            '[data-tour="account-form-submit"]',
            'button:has-text("下一步")',
            'button:has-text("Next")',
        ),
        timeout_s=15,
        require_enabled=True,
    )
    if next_btn is None:
        raise AdminImportError("点「下一步」失败：按钮未出现")
    next_btn.click(timeout=8000)
    page.wait_for_timeout(1200)
    print("[*] create account step2 (oauth)")


def select_manual_and_generate_auth_url(page: Any) -> str:
    """手动授权 + 生成授权链接，返回 auth URL。"""
    from .browser_wait import wait_visible

    # 等 step2 OAuth 区域渲染
    wait_visible(
        page,
        (
            'input[type="radio"][value="manual"]',
            'label:has-text("手动授权")',
            'label:has-text("Manual Authorization")',
            'button:has-text("生成授权链接")',
            'button:has-text("Generate Auth URL")',
        ),
        timeout_s=25,
    )

    manual = page.locator('input[type="radio"][value="manual"]')
    if manual.count() > 0:
        try:
            manual.first.check(force=True)
        except Exception:
            manual.first.click(force=True)
    else:
        _click_any(
            page,
            (
                'label:has-text("手动授权")',
                'label:has-text("Manual Authorization")',
                'span:has-text("手动授权")',
            ),
        )
    page.wait_for_timeout(500)

    auth_url = ""

    def _on_response(resp: Any) -> None:
        nonlocal auth_url
        try:
            rurl = str(resp.url or "")
            if "generate-auth-url" not in rurl:
                return
            if resp.status != 200:
                return
            data = resp.json()
            payload = data.get("data") if isinstance(data, dict) else None
            if isinstance(payload, dict):
                auth_url = str(payload.get("auth_url") or payload.get("url") or "").strip()
            if not auth_url and isinstance(data, dict):
                auth_url = str(data.get("auth_url") or "").strip()
            if auth_url:
                print(f"[*] intercepted auth_url len={len(auth_url)}")
        except Exception:
            pass

    page.on("response", _on_response)

    gen_btn = wait_visible(
        page,
        (
            'button:has-text("生成授权链接")',
            'button:has-text("生成授权 URL")',
            'button:has-text("Generate Auth URL")',
            'button:has-text("Generate")',
        ),
        timeout_s=20,
        require_enabled=True,
    )
    if gen_btn is None:
        raise AdminImportError("找不到「生成授权链接」")
    gen_btn.click(timeout=8000)

    deadline = time.time() + 35
    while time.time() < deadline and not auth_url:
        try:
            for inp in page.locator("input[readonly], input.font-mono").all():
                val = inp.input_value()
                if val and "auth.openai.com" in val:
                    auth_url = val.strip()
                    break
        except Exception:
            pass
        page.wait_for_timeout(500)

    if not auth_url:
        raise AdminImportError("未拿到 auth_url")
    print(f"[*] auth_url ready host={urlparse(auth_url).netloc}")
    return auth_url


def paste_callback_and_complete(page: Any, callback_or_code: str) -> None:
    """把回调 URL/code 填回授权码框并点完成授权。"""
    from .browser_wait import wait_visible

    text = (callback_or_code or "").strip()
    if not text:
        raise AdminImportError("empty callback/code")

    ta = wait_visible(page, ("textarea",), timeout_s=25)
    if ta is None:
        raise AdminImportError("授权码 textarea 未出现")
    ta.click(timeout=3000)
    ta.fill("")
    ta.fill(text)
    page.wait_for_timeout(400)

    done = wait_visible(
        page,
        (
            'button:has-text("完成授权")',
            'button:has-text("Complete")',
            'button:has-text("Verify")',
            'button:has-text("验证")',
            'button.btn-primary:has-text("授权")',
        ),
        timeout_s=15,
        require_enabled=True,
    )
    if done is None:
        raise AdminImportError("点「完成授权」失败：按钮未出现")
    done.click(timeout=8000)
    page.wait_for_timeout(2500)
    print("[*] complete auth clicked")


def extract_code_from_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "code=" in raw or raw.startswith("http"):
        try:
            qs = parse_qs(urlparse(raw).query)
            code = (qs.get("code") or [""])[0]
            if code:
                return code
        except Exception:
            pass
        return raw
    return raw


def admin_env() -> tuple[str, str, str]:
    base = (
        os.getenv("SUB2API_BASE_URL")
        or os.getenv("ADMIN_BASE_URL")
        or "https://api4kimi8.org"
    ).rstrip("/")
    email = (os.getenv("SUB2API_ADMIN_EMAIL") or os.getenv("ADMIN_EMAIL") or "").strip()
    password = (
        os.getenv("SUB2API_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD") or ""
    ).strip()
    if not email or not password:
        raise AdminImportError(
            "Missing SUB2API_ADMIN_EMAIL / SUB2API_ADMIN_PASSWORD "
            "(or ADMIN_EMAIL / ADMIN_PASSWORD)"
        )
    return base, email, password


def _wait_admin_shell_ready(page: Any, *, timeout_s: float = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = page.url or ""
        if "/login" not in url:
            # 侧栏或主布局
            for sel in (
                "aside",
                "nav",
                'a[href*="/admin/"]',
                'text=账号管理',
                'text=Dashboard',
                'text=仪表盘',
            ):
                try:
                    if page.locator(sel).count() > 0:
                        page.wait_for_timeout(800)
                        return
                except Exception:
                    continue
        page.wait_for_timeout(400)
    # 最后再给一次 network 等待
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def _wait_page_fully_loaded(page: Any) -> None:
    """等 DOM + 网络大致稳定。"""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("load", timeout=30000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    # SPA 再稳一会儿
    page.wait_for_timeout(1500)


def _dismiss_popups_with_esc(page: Any) -> None:
    """完全加载后连按 ESC 清 onboarding/公告等弹窗。"""
    print("[*] dismiss popups with Escape")
    for _ in range(4):
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(350)
    # 再点常见关闭按钮兜底
    _click_any(
        page,
        (
            'button[aria-label="Close"]',
            'button[aria-label="close"]',
            'button:has-text("关闭")',
            'button:has-text("Close")',
            'button:has-text("跳过")',
            'button:has-text("Skip")',
            'button:has-text("我知道了")',
            'button:has-text("Got it")',
            'button:has-text("稍后")',
        ),
        timeout_ms=800,
    )
    page.wait_for_timeout(400)


def _goto_accounts_via_nav(page: Any) -> bool:
    """点侧栏「账号管理」。"""
    selectors = (
        'a[href="/admin/accounts"]',
        'a[href*="/admin/accounts"]',
        'aside a:has-text("账号管理")',
        'nav a:has-text("账号管理")',
        'a:has-text("账号管理")',
        'button:has-text("账号管理")',
        'aside a:has-text("Accounts")',
        'a:has-text("Accounts")',
        '#sidebar-channel-manage a[href*="accounts"]',
    )
    if _click_any(page, selectors, timeout_ms=8000):
        page.wait_for_timeout(1200)
        # 确认到了 accounts
        deadline = time.time() + 20
        while time.time() < deadline:
            if "/admin/accounts" in (page.url or ""):
                return True
            # 页面上有添加账号也算到了
            if page.locator('button:has-text("添加账号"), button:has-text("Create Account")').count() > 0:
                return True
            page.wait_for_timeout(400)
        return "/admin/accounts" in (page.url or "")
    return False


def _has_login_form(page: Any) -> bool:
    try:
        return page.locator('#email, input[type="email"]').count() > 0 and page.locator(
            '#password, input[type="password"]'
        ).count() > 0
    except Exception:
        return False


def _click_any(
    page: Any, selectors: tuple[str, ...], *, timeout_ms: int = 8000
) -> bool:
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
