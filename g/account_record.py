# Layer: L0 公理层
# Contract: 一行账号记录 email|password|access_token；字段非空且可 round-trip。
# Invariant: password/token 不得含 | 或换行，避免导入歧义。

from __future__ import annotations

from dataclasses import dataclass


class AccountRecordError(ValueError):
    """账号记录格式不合法。"""


@dataclass(frozen=True, slots=True)
class AccountRecord:
    email: str
    password: str
    access_token: str


def format_account_record(email: str, password: str, access_token: str) -> str:
    email = (email or "").strip()
    password = password or ""
    access_token = (access_token or "").strip()
    _reject_field(email, "email")
    _reject_field(password, "password")
    _reject_field(access_token, "access_token")
    if "@" not in email:
        raise AccountRecordError("email missing @")
    line = f"{email}|{password}|{access_token}"
    # round-trip 校验，确保写入格式可再解析
    parsed = parse_account_record(line)
    if (
        parsed.email != email
        or parsed.password != password
        or parsed.access_token != access_token
    ):
        raise AccountRecordError("record round-trip mismatch")
    return line


def parse_account_record(line: str) -> AccountRecord:
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        raise AccountRecordError("empty record")
    parts = raw.split("|", 2)
    if len(parts) != 3:
        raise AccountRecordError("expected email|password|access_token")
    email, password, access_token = (p.strip() for p in parts)
    if not email or not password or not access_token:
        raise AccountRecordError("empty field")
    if "@" not in email:
        raise AccountRecordError("email missing @")
    return AccountRecord(email=email, password=password, access_token=access_token)


def _reject_field(value: str, name: str) -> None:
    if not value:
        raise AccountRecordError(f"{name} empty")
    if any(ch in value for ch in ("|", "\n", "\r")):
        raise AccountRecordError(f"{name} contains delimiter")
