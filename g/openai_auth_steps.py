# Layer: L1 积木层（聚合导出）
# Contract: 兼容旧 import 路径 openai_auth_steps.*

from .openai_auth_entry import (
    RegistrationError,
    authorize_continue,
    register_password,
    set_device_cookie,
    start_oauth,
)
from .openai_account_steps import (
    bootstrap_chatgpt,
    create_account,
    exchange_oauth_token,
    send_otp,
    validate_otp,
)

__all__ = [
    "RegistrationError",
    "set_device_cookie",
    "start_oauth",
    "authorize_continue",
    "register_password",
    "send_otp",
    "validate_otp",
    "create_account",
    "exchange_oauth_token",
    "bootstrap_chatgpt",
]
