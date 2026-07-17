# Layer: L2 流程层
# Contract: 完整 ChatGPT 注册；成功返回 email/password/access_token。
# Boundary: L2 编排 L1（邮箱/auth steps/session）；凭据落盘由 CLI 负责。
# Why: 相对 Grok 取 sso，本流程在同一 session 打开 /api/auth/session 取 accessToken。

from __future__ import annotations

import random
import secrets
import string
import uuid
from dataclasses import dataclass

from .email_service import EmailService
from .http_session import create_session
from .openai_auth_steps import (
    RegistrationError,
    authorize_continue,
    bootstrap_chatgpt,
    create_account,
    exchange_oauth_token,
    register_password,
    send_otp,
    set_device_cookie,
    start_oauth,
    validate_otp,
)
from .session_token import fetch_access_token

__all__ = ["RegisterFlow", "RegisterResult", "RegistrationError"]


@dataclass(slots=True)
class RegisterResult:
    email: str
    password: str
    access_token: str
    device_id: str = ""


class RegisterFlow:
    """单账号注册流程（可被多线程各自实例化）。"""

    def __init__(self, proxy: str = "", impersonate: str = ""):
        self.proxy = (proxy or "").strip()
        self.session = create_session(proxy=self.proxy, impersonate=impersonate)
        self.device_id = str(uuid.uuid4())
        self.code_verifier = ""
        self.email_service = EmailService()

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    def register_one(self) -> RegisterResult:
        email = None
        try:
            _jwt, email = self.email_service.create_email()
            if not email:
                raise RegistrationError("create_email failed")

            password = _random_password()
            print(f"[*] 开始注册: {email}")

            self.code_verifier, did_hint = start_oauth(self.session, email)
            if did_hint:
                self.device_id = did_hint
            set_device_cookie(self.session, self.device_id)

            page_type = authorize_continue(self.session, self.device_id, email)
            print(f"[*] authorize/continue page={page_type or '?'}")

            if page_type != "email_otp_verification":
                register_password(self.session, self.device_id, email, password)
                send_otp(self.session)

            code = self.email_service.fetch_verification_code(email)
            if not code:
                raise RegistrationError("otp timeout")
            print(f"[*] OTP ok")
            next_page = validate_otp(self.session, self.device_id, code)
            print(f"[*] after OTP page={next_page or '?'}")

            auth_code = None
            if next_page != "email_otp_verification":
                # 单名，匹配 platform 注册页习惯
                auth_code = create_account(
                    self.session,
                    self.device_id,
                    _random_first_name(),
                    _random_birthdate(),
                )
                print(f"[*] create_account ok code={'yes' if auth_code else 'no'}")

            bootstrap_chatgpt(self.session)

            # 主路径：同一 session 打开 session API
            access_token = fetch_access_token(self.session)
            if not access_token and auth_code:
                # 兜底：OAuth code 换 token，再带 hint 读 session
                exchanged = exchange_oauth_token(
                    self.session, self.code_verifier, auth_code
                )
                if exchanged:
                    access_token = fetch_access_token(
                        self.session, access_hint=exchanged
                    ) or exchanged

            if not access_token:
                raise RegistrationError("empty accessToken from /api/auth/session")

            return RegisterResult(
                email=email,
                password=password,
                access_token=access_token,
                device_id=self.device_id,
            )
        finally:
            if email:
                try:
                    self.email_service.delete_email(email)
                except Exception:
                    pass


def _random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    base = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    base += [secrets.choice(chars) for _ in range(max(0, length - 4))]
    random.shuffle(base)
    return "".join(base)


def _random_first_name() -> str:
    return random.choice(
        ["James", "Robert", "John", "Michael", "Emma", "Olivia", "Neo", "Liam"]
    )


def _random_birthdate() -> str:
    return (
        f"{random.randint(1985, 2005):04d}-"
        f"{random.randint(1, 12):02d}-"
        f"{random.randint(1, 28):02d}"
    )
