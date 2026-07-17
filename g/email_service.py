# Layer: L1 积木层
# Contract: 经 Outlook Email Plus /api/external/* 领取邮箱、取验证码、释放/完成租约。
# Boundary: 不直连 Cloudflare Temp Mail；上游契约固定为 X-API-Key + pool claim。
# Why: 注册机只依赖邮箱池中台，避免自建 CF Worker 协议与密钥分叉。

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

import requests
from dotenv import load_dotenv


def _looks_like_date(digits: str) -> bool:
    if not digits or not digits.isdigit():
        return False
    if len(digits) == 4:
        n = int(digits)
        return 1900 <= n <= 2099
    if len(digits) == 8:
        year, month, day = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
        return 1900 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31
    return False


def _normalize_mail_text(text: str) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def extract_verification_code(text: str) -> str | None:
    """本地兜底抽码；主路径优先走 OEP verification-code。"""
    if not text:
        return None
    raw = text.strip()
    plain = _normalize_mail_text(text)
    delim = r"\s*(?:[:：]|\bis\b|是|为|です)[\s:：]*"
    cn_ja_ko_kw = r"验证码|认证码|确认码|認証コード|인증\s*코드|코드"
    en_kw = r"verification\s*code|confirm(?:ation)?\s*code|security\s*code|passcode|OTP|pin\s*code"
    all_kw = f"{cn_ja_ko_kw}|{en_kw}"
    patterns = [
        re.compile(rf"\bcode{delim}(\d{{4,12}})\b", re.I),
        re.compile(rf"(?:{all_kw}){delim}(\d{{4,12}})\b", re.I),
        re.compile(rf"\bcode{delim}([A-Za-z0-9-]{{4,12}})\b", re.I),
        re.compile(rf"(?:{all_kw}){delim}([A-Za-z0-9-]{{4,12}})\b", re.I),
    ]
    for source in (plain, raw):
        for pattern in patterns:
            match = pattern.search(source)
            if match and match.group(1) and not _looks_like_date(match.group(1).replace("-", "")):
                return match.group(1)
    standalone = re.search(r"(?:^|\s)(\d{4,12})(?:\s|$|\.|,)", plain, re.M)
    if standalone and not _looks_like_date(standalone.group(1)):
        return standalone.group(1)
    return None


class EmailService:
    """Outlook Email Plus 邮箱池适配。"""

    def __init__(self) -> None:
        load_dotenv()
        self.base_url = (
            os.getenv("OEP_BASE_URL")
            or os.getenv("MAIL_BASE_URL")
            or ""
        ).rstrip("/")
        if self.base_url and not self.base_url.startswith("http"):
            self.base_url = f"https://{self.base_url}"

        self.api_key = (
            os.getenv("OEP_API_KEY")
            or os.getenv("MAIL_API_KEY")
            or os.getenv("MAIL_ADMIN_PASSWORD")
            or ""
        ).strip()
        self.provider = (os.getenv("OEP_PROVIDER") or "outlook").strip()
        self.project_key = (os.getenv("OEP_PROJECT_KEY") or "gptsignup").strip()
        self.caller_id = (
            os.getenv("OEP_CALLER_ID") or os.getenv("HOSTNAME") or "gptsignup"
        ).strip()

        if not self.base_url:
            raise ValueError("Missing: OEP_BASE_URL (or MAIL_BASE_URL)")
        if not self.api_key:
            raise ValueError("Missing: OEP_API_KEY")
        if self.provider == "cloudflare_temp_mail":
            raise ValueError(
                "OEP_PROVIDER=cloudflare_temp_mail 已弃用；请改用 outlook/imap 等长期邮箱池"
            )

        self._headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # email -> lease metadata
        self._leases: dict[str, dict[str, Any]] = {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def create_email(self) -> tuple[str | None, str | None]:
        """领取邮箱：POST /api/external/pool/claim-random。

        返回 (claim_token, email)，保持旧调用方解构兼容。
        """
        task_id = f"gpt-{uuid.uuid4().hex[:16]}"
        body: dict[str, Any] = {
            "caller_id": self.caller_id,
            "task_id": task_id,
            "provider": self.provider,
        }
        if self.project_key:
            body["project_key"] = self.project_key
        try:
            res = requests.post(
                self._url("/api/external/pool/claim-random"),
                headers=self._headers,
                json=body,
                timeout=20,
            )
            payload = res.json() if res.content else {}
            if not payload.get("success"):
                print(
                    f"[-] 领取邮箱失败: {payload.get('code')} - {payload.get('message')}"
                )
                return None, None
            data = payload.get("data") or {}
            email = data.get("email")
            claim_token = data.get("claim_token")
            account_id = data.get("account_id")
            if not email or not claim_token or account_id is None:
                print(f"[-] 领取邮箱失败: 响应缺字段 - {data}")
                return None, None
            self._leases[email] = {
                "account_id": account_id,
                "claim_token": claim_token,
                "caller_id": self.caller_id,
                "task_id": task_id,
            }
            return claim_token, email
        except Exception as exc:
            print(f"[-] 领取邮箱失败: {exc}")
            return None, None

    def fetch_verification_code(self, email: str, max_attempts: int = 40) -> str | None:
        """优先 OEP verification-code；失败再读 messages 本地抽码。"""
        if email not in self._leases:
            print(f"[-] 无法获取验证码: 未找到租约 ({email})")
            return None

        interval = 2
        params = {
            "email": email,
            "since_minutes": 15,
            "folder": "inbox",
        }
        for attempt in range(max_attempts):
            try:
                res = requests.get(
                    self._url("/api/external/verification-code"),
                    headers=self._headers,
                    params=params,
                    timeout=20,
                )
                payload = res.json() if res.content else {}
                if payload.get("success"):
                    data = payload.get("data") or {}
                    code = data.get("code") or data.get("verification_code")
                    if code:
                        return str(code).replace("-", "")
                # fallback: list messages and extract locally
                code = self._fetch_code_from_messages(email)
                if code:
                    return code
            except Exception:
                pass
            time.sleep(interval)
            if attempt > 0 and attempt % 5 == 0:
                interval = min(interval + 1, 5)
        return None

    def _fetch_code_from_messages(self, email: str) -> str | None:
        res = requests.get(
            self._url("/api/external/messages"),
            headers=self._headers,
            params={"email": email, "top": 10, "since_minutes": 15},
            timeout=20,
        )
        payload = res.json() if res.content else {}
        if not payload.get("success"):
            return None
        data = payload.get("data") or {}
        emails = data.get("emails") or data.get("messages") or []
        for mail in emails:
            for field in ("subject", "content", "html_content", "text", "html"):
                code = extract_verification_code(str(mail.get(field) or ""))
                if code:
                    return code.replace("-", "")
        return None

    def complete_email(self, address: str, *, result: str = "success", detail: str = "") -> bool:
        """任务成功/终态：POST /api/external/pool/claim-complete。"""
        return self._finish(address, mode="complete", result=result, detail=detail)

    def delete_email(self, address: str) -> bool:
        """中途放弃：POST /api/external/pool/claim-release。"""
        return self._finish(address, mode="release")

    def _finish(
        self,
        address: str,
        *,
        mode: str,
        result: str = "success",
        detail: str = "",
    ) -> bool:
        if not address:
            return False
        lease = self._leases.pop(address, None)
        if not lease:
            return False
        body = {
            "account_id": lease["account_id"],
            "claim_token": lease["claim_token"],
            "caller_id": lease["caller_id"],
            "task_id": lease["task_id"],
        }
        try:
            if mode == "complete":
                body["result"] = result
                if detail:
                    body["detail"] = detail
                path = "/api/external/pool/claim-complete"
            else:
                body["reason"] = detail or "registration_aborted"
                path = "/api/external/pool/claim-release"
            res = requests.post(
                self._url(path),
                headers=self._headers,
                json=body,
                timeout=20,
            )
            payload = res.json() if res.content else {}
            return bool(payload.get("success"))
        except Exception:
            return False
