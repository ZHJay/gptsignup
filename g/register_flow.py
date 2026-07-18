# Layer: L2 流程层
# Contract: ChatGPT 网页注册后保活登录态 → Sub2API 添加 OpenAI 账号 → OAuth+Tiger SMS。
# Boundary: L2 编排 L1（邮箱/浏览器注册/管理端/短信）；不再依赖 accessToken 成功条件。
# Why: AT 不再重要；成功标准是账号进入 api4kimi8.org 管理端。

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from .admin_import_steps import (
    AdminImportError,
    admin_env,
    ensure_admin_login,
    extract_code_from_url,
    open_accounts_and_create_openai,
    paste_callback_and_complete,
    select_manual_and_generate_auth_url,
)
from .browser_oauth_steps import click_choose_account, page_is_choose_account
from .browser_phone_steps import (
    BrowserPhoneError,
    page_has_otp,
    page_needs_phone,
    submit_phone_national,
    submit_sms_code,
    wait_phone_or_done,
)
from .browser_session import BrowserSession
from .browser_signup_steps import (
    BrowserSignupError,
    click_login,
    submit_email,
    submit_otp,
    submit_profile,
    wait_otp_page,
    wait_profile_page,
    wait_registered,
)
from .email_service import EmailService
from .phone_service import PhoneService, TigerSmsError
from .session_token import fetch_access_token_from_browser

__all__ = ["RegisterFlow", "RegisterResult", "RegistrationError"]

PASSWORDLESS_MARKER = "passwordless"


class RegistrationError(RuntimeError):
    """单次注册/导入失败。"""


@dataclass(slots=True)
class RegisterResult:
    email: str
    password: str
    access_token: str  # 可选；空表示未取到，不影响成功
    imported: bool = False
    detail: str = ""


class RegisterFlow:
    """单账号：注册 ChatGPT + 导入 Sub2API（浏览器保活）。"""

    def __init__(self, proxy: str = "", impersonate: str = ""):
        self.proxy = (proxy or os.getenv("PROXY") or "").strip()
        self._impersonate = impersonate or ""
        self.email_service = EmailService()
        self._browser: BrowserSession | None = None

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

    def _retire_dirty_email(self, email: str, detail: str) -> bool:
        try:
            return bool(
                self.email_service.complete_email(
                    email, result="provider_blocked", detail=detail[:200]
                )
            )
        except Exception:
            return False

    def register_one(self) -> RegisterResult:
        email = None
        finished = False
        browser: BrowserSession | None = None
        try:
            _claim, email = self.email_service.create_email()
            if not email:
                raise RegistrationError("create_email failed")

            print(f"[*] 开始注册(browser): {email}")
            browser = BrowserSession(proxy=self.proxy)
            self._browser = browser
            browser.start()

            # ---- ChatGPT 注册；主 tab 永远留在已登录的 ChatGPT ----
            browser.open("https://chatgpt.com/", wait_cf=True)
            chatgpt_page = browser.page
            click_login(chatgpt_page)
            browser.wait_cf_clear()
            submit_email(chatgpt_page, email)

            try:
                wait_otp_page(chatgpt_page)
            except BrowserSignupError as exc:
                msg = str(exc)
                if "not signup-ready" in msg or "login_password" in msg:
                    if self._retire_dirty_email(email, msg):
                        finished = True
                    raise RegistrationError(msg) from exc
                raise RegistrationError(msg) from exc

            code = self.email_service.fetch_verification_code(email)
            if not code:
                raise RegistrationError("otp timeout")
            print(f"[*] OTP ok code_len={len(code)}")
            submit_otp(chatgpt_page, code)

            wait_profile_page(chatgpt_page)
            submit_profile(chatgpt_page)
            wait_registered(chatgpt_page)
            # 确保主 tab 停在 chatgpt.com 已登录态
            try:
                if "chatgpt.com" not in (chatgpt_page.url or ""):
                    chatgpt_page.goto(
                        "https://chatgpt.com/",
                        wait_until="domcontentloaded",
                        timeout=120_000,
                    )
                    chatgpt_page.wait_for_timeout(1000)
            except Exception:
                pass
            print(f"[*] ChatGPT registered, keep tab url={chatgpt_page.url}")

            # AT 可选，失败不阻断；在 chatgpt tab 内读
            access_token = ""
            try:
                access_token = fetch_access_token_from_browser(browser) or ""
            except Exception as exc:
                print(f"[!] skip AT: {exc}")

            # ---- Sub2API：另开 tab，不碰 ChatGPT 主 tab ----
            imported = self._import_to_sub2api(browser, email, chatgpt_page)

            try:
                self.email_service.complete_email(
                    email,
                    result="success",
                    detail="chatgpt_registered_and_imported"
                    if imported
                    else "chatgpt_registered_import_pending",
                )
            except Exception:
                pass
            finished = True
            try:
                chatgpt_page.bring_to_front()
            except Exception:
                pass
            print("[*] 浏览器保持打开（ChatGPT 主 tab + Sub2API tab）；不自动关闭")
            return RegisterResult(
                email=email,
                password=PASSWORDLESS_MARKER,
                access_token=access_token,
                imported=imported,
                detail="imported" if imported else "registered_only",
            )
        except (BrowserSignupError, AdminImportError, BrowserPhoneError, TigerSmsError) as exc:
            msg = str(exc)
            if email and ("not signup-ready" in msg or "login_password" in msg):
                if self._retire_dirty_email(email, msg):
                    finished = True
            raise RegistrationError(msg) from exc
        finally:
            if email and not finished:
                try:
                    self.email_service.delete_email(email)
                except Exception:
                    pass
            # Invariant: 永不自动 close 浏览器；由进程退出或用户手动关窗口。

    def _import_to_sub2api(
        self, browser: BrowserSession, email: str, chatgpt_page: Any
    ) -> bool:
        base, admin_email, admin_password = admin_env()
        # Why: 主 tab 留给已登录 ChatGPT；管理端 / OAuth 各开新 tab。
        admin_page = browser.new_page()
        oauth_page = browser.new_page()

        ensure_admin_login(
            admin_page, base_url=base, email=admin_email, password=admin_password
        )
        open_accounts_and_create_openai(admin_page, email)
        auth_url = select_manual_and_generate_auth_url(admin_page)

        print("[*] open oauth url in new tab (same context, shared cookies)")
        oauth_page.goto(auth_url, wait_until="domcontentloaded", timeout=120_000)
        oauth_page.wait_for_timeout(1500)

        callback = self._complete_oauth_with_phone(oauth_page, preferred_email=email)
        if not callback:
            raise AdminImportError("oauth finished without callback/code")

        code_or_url = extract_code_from_url(callback) or callback
        print(f"[*] paste callback into admin code_len={len(code_or_url)}")
        admin_page.bring_to_front()
        paste_callback_and_complete(admin_page, code_or_url)
        print(f"[*] Sub2API import done for {email}")
        # 不关闭任何 tab / 浏览器
        try:
            chatgpt_page.bring_to_front()
        except Exception:
            pass
        return True

    def _complete_oauth_with_phone(
        self, page: Any, *, preferred_email: str = ""
    ) -> str:
        """在 OAuth 页处理 Choose account / 同意 / 手机验证。

        Invariant:
        - Choose account 必须先点账号再继续
        - 手机号只来自 Tiger getNumberV2
        - 验证码只来自 Tiger getStatusV2；禁止空码/猜测码
        - 收码硬超时 120s，超时 cancel 激活并失败
        """
        phone_svc = PhoneService()
        activation = None
        phone_submitted = False
        sms_submitted = False
        account_chosen = False
        # 整段 OAuth 上限；短信等待单独 120s
        deadline = time.time() + int(os.getenv("OAUTH_PHONE_TIMEOUT_S") or 300)
        sms_wait_s = 120  # Contract: 用户要求固定 120s，不读更长 env 放宽
        last_state = ""

        while time.time() < deadline:
            url = page.url or ""
            if "code=" in url or "localhost" in url or "127.0.0.1" in url:
                print(f"[*] oauth callback url={url[:160]}")
                if activation is not None:
                    try:
                        phone_svc.complete(activation.activation_id)
                    except Exception:
                        pass
                return url

            # 优先用即时 DOM 判断，避免误点
            on_otp = page_has_otp(page)
            on_phone = page_needs_phone(page) and not on_otp
            on_choose = page_is_choose_account(page) and not on_otp and not on_phone

            # ---- Choose account（进 ChatGPT 授权后常见）----
            if on_choose:
                if account_chosen:
                    page.wait_for_timeout(800)
                    continue
                ok = click_choose_account(page, preferred_email=preferred_email)
                if not ok:
                    # 再等 DOM 渲染后重试一次
                    page.wait_for_timeout(1500)
                    ok = click_choose_account(page, preferred_email=preferred_email)
                if not ok:
                    raise BrowserPhoneError(
                        f"choose account page but no account clicked url={page.url}"
                    )
                account_chosen = True
                page.wait_for_timeout(1500)
                continue

            if on_otp:
                if sms_submitted:
                    page.wait_for_timeout(1000)
                    continue
                if activation is None:
                    raise BrowserPhoneError(
                        "otp page without tiger activation; refuse to type any code"
                    )
                print(
                    f"[*] waiting Tiger SMS code via getStatusV2 "
                    f"(timeout={sms_wait_s}s, activation={activation.activation_id})"
                )
                # Why: 只轮询 API；等待期间不点 Continue、不填任何输入框。
                sms = phone_svc.wait_code(
                    activation.activation_id,
                    max_wait_seconds=sms_wait_s,
                    interval_seconds=3.0,
                )
                if not sms:
                    try:
                        phone_svc.cancel(activation.activation_id)
                    except Exception:
                        pass
                    raise BrowserPhoneError(
                        f"sms code timeout after {sms_wait_s}s "
                        f"(activation={activation.activation_id}); aborted"
                    )
                sms_digits = "".join(ch for ch in str(sms) if ch.isdigit())
                if len(sms_digits) < 4:
                    try:
                        phone_svc.cancel(activation.activation_id)
                    except Exception:
                        pass
                    raise BrowserPhoneError(
                        f"tiger returned invalid sms code: {sms!r}; refuse to submit"
                    )
                print(f"[*] tiger sms ok len={len(sms_digits)} — submit only this code")
                submit_sms_code(page, sms_digits)
                sms_submitted = True
                page.wait_for_timeout(2000)
                continue

            if on_phone:
                if phone_submitted:
                    # 已提交号码，静等跳到 OTP，禁止重复乱填
                    page.wait_for_timeout(1000)
                    continue
                if activation is None:
                    retries = int(os.getenv("TIGER_SMS_NUMBER_RETRIES") or 3)
                    last_err = None
                    for i in range(max(1, retries)):
                        try:
                            activation = phone_svc.get_number()
                            print(
                                f"[*] tiger number={activation.national_number} "
                                f"id={activation.activation_id} cost={activation.activation_cost}"
                            )
                            break
                        except TigerSmsError as exc:
                            last_err = exc
                            print(f"[!] getNumberV2 retry {i+1}: {exc}")
                            time.sleep(2)
                    if activation is None:
                        raise BrowserPhoneError(f"tiger get number failed: {last_err}")
                submit_phone_national(page, activation.national_number)
                phone_submitted = True
                sms_submitted = False
                page.wait_for_timeout(1500)
                continue

            state = wait_phone_or_done(page, timeout_s=2)
            if state != last_state:
                print(f"[*] oauth state={state} url={url[:120]}")
                last_state = state

            if state == "done":
                if activation is not None:
                    try:
                        phone_svc.complete(activation.activation_id)
                    except Exception:
                        pass
                return page.url or ""
            if state == "error":
                raise BrowserPhoneError(f"oauth error url={url}")
            if state in ("otp", "phone"):
                # 下一轮由 on_otp/on_phone 精确处理
                continue

            # 仅在非手机号/非 OTP/非选账号页点同意类按钮
            if not on_otp and not on_phone and not on_choose:
                # URL/标题再扫一次 choose account（文案延迟渲染）
                if page_is_choose_account(page):
                    continue
                for sel in (
                    'button:has-text("Continue")',
                    'button:has-text("Allow")',
                    'button:has-text("Accept")',
                    'button:has-text("Agree")',
                    'button:has-text("Authorize")',
                    'button:has-text("继续")',
                    'button:has-text("允许")',
                    'button[type="submit"]',
                ):
                    loc = page.locator(sel)
                    try:
                        if (
                            loc.count() > 0
                            and loc.first.is_visible()
                            and loc.first.is_enabled()
                        ):
                            text = (loc.first.inner_text() or "").lower()
                            # 避免在验证相关按钮上空点
                            if any(
                                k in text
                                for k in ("resend", "code", "verify", "验证", "重发")
                            ):
                                continue
                            loc.first.click(timeout=3000)
                            page.wait_for_timeout(1000)
                            break
                    except Exception:
                        continue
            page.wait_for_timeout(800)

        if activation is not None:
            try:
                phone_svc.cancel(activation.activation_id)
            except Exception:
                pass
        raise BrowserPhoneError("oauth+phone timeout")
