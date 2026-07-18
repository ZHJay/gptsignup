# Layer: L1 积木层
# Contract: 等待某个可见可点控件出现；统一「路由到了但 DOM 未挂载」等待。
# Boundary: 仅 Playwright page 查询，无业务语义。

from __future__ import annotations

import time
from typing import Any, Iterable


def wait_visible(
    page: Any,
    selectors: Iterable[str],
    *,
    timeout_s: float = 30,
    require_enabled: bool = False,
) -> Any | None:
    """轮询 selectors，返回第一个可见（可选 enabled）locator 元素。"""
    sels = tuple(selectors)
    deadline = time.time() + max(1.0, timeout_s)
    while time.time() < deadline:
        for sel in sels:
            loc = page.locator(sel)
            try:
                n = loc.count()
                for i in range(min(n, 8)):
                    el = loc.nth(i)
                    if not el.is_visible():
                        continue
                    if require_enabled:
                        try:
                            if not el.is_enabled():
                                continue
                        except Exception:
                            pass
                    return el
            except Exception:
                continue
        page.wait_for_timeout(300)
    return None


def wait_url_contains(page: Any, needles: Iterable[str], *, timeout_s: float = 30) -> bool:
    needles_l = tuple(n.lower() for n in needles)
    deadline = time.time() + max(1.0, timeout_s)
    while time.time() < deadline:
        url = (page.url or "").lower()
        if any(n in url for n in needles_l):
            return True
        page.wait_for_timeout(250)
    return False


def page_snip(page: Any, limit: int = 200) -> str:
    try:
        return (page.locator("body").inner_text(timeout=1500) or "")[:limit]
    except Exception:
        return ""
