# Layer: L1 积木层
# Contract: 向 sentinel 请求 PoW，返回 openai-sentinel-token 头值。
# Boundary: 单次外部 HTTP；失败抛 RuntimeError，不重试策略。

from __future__ import annotations

import base64
import json
import random
import time
import uuid

from curl_cffi.requests import Session

from .openai_headers import SEC_CH_UA, SENTINEL_URL, USER_AGENT


class SentinelTokenGenerator:
    """OpenAI Sentinel PoW（算法需与官方 sdk 期望一致）。"""

    MAX_ATTEMPTS = 500_000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id: str, ua: str):
        self.device_id = device_id
        self.user_agent = ua
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str) -> str:
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= h >> 16
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= h >> 16
        return format(h & 0xFFFFFFFF, "08x")

    def _config(self) -> list:
        perf_now = random.uniform(1000, 50000)
        return [
            "1920x1080",
            time.strftime(
                "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)",
                time.gmtime(),
            ),
            4294705152,
            random.random(),
            self.user_agent,
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
            None,
            None,
            "en-US",
            random.random(),
            "plugins-undefined",
            "location",
            "Object",
            perf_now,
            self.sid,
            "",
            random.choice([4, 8, 12, 16]),
            time.time() * 1000 - perf_now,
        ]

    @staticmethod
    def _b64(data) -> str:
        return base64.b64encode(
            json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).decode("ascii")

    def requirements_token(self) -> str:
        data = self._config()
        data[3] = 1
        data[9] = round(random.uniform(5, 50))
        return "gAAAAAC" + self._b64(data)

    def pow_token(self, seed: str, difficulty: str) -> str:
        start = time.time()
        data = self._config()
        difficulty = str(difficulty or "0")
        for i in range(self.MAX_ATTEMPTS):
            data[3] = i
            data[9] = round((time.time() - start) * 1000)
            payload = self._b64(data)
            if self._fnv1a_32(seed + payload)[: len(difficulty)] <= difficulty:
                return "gAAAAAB" + payload + "~S"
        return "gAAAAAB" + self.ERROR_PREFIX + self._b64(str(None))


def build_sentinel_token(session: Session, device_id: str, flow: str) -> str:
    """返回 openai-sentinel-token 头字符串。"""
    gen = SentinelTokenGenerator(device_id, USER_AGENT)
    resp = session.post(
        SENTINEL_URL,
        data=json.dumps(
            {"p": gen.requirements_token(), "id": device_id, "flow": flow}
        ),
        headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
            "Origin": "https://sentinel.openai.com",
            "User-Agent": USER_AGENT,
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
        timeout=20,
    )
    try:
        data = resp.json() if resp.text else {}
    except Exception as exc:
        raise RuntimeError(f"sentinel_json_error: {exc}") from exc

    token = str(data.get("token") or "").strip()
    if resp.status_code != 200 or not token:
        raise RuntimeError(f"sentinel_req_failed_{resp.status_code}")

    pow_data = data.get("proofofwork") or {}
    if pow_data.get("required") and pow_data.get("seed"):
        p_value = gen.pow_token(
            str(pow_data.get("seed") or ""),
            str(pow_data.get("difficulty") or "0"),
        )
    else:
        p_value = gen.requirements_token()

    return json.dumps(
        {"p": p_value, "t": "", "c": token, "id": device_id, "flow": flow},
        separators=(",", ":"),
    )
