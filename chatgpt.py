#!/usr/bin/env python3
# Layer: L2 流程层（CLI 边界）
# Contract: 注册 ChatGPT 并导入 Sub2API；浏览器永不自动关闭。
# Boundary: 仅编排 RegisterFlow + 文件写入。
# Why: 成功后需保留 ChatGPT 登录 tab；进程保活直到用户 Ctrl+C。
# Risk: 浏览器常驻，workers 必须 1。

from __future__ import annotations

import argparse
import os
import signal
import time
from datetime import datetime

from dotenv import load_dotenv

from g.account_record import format_account_record
from g.register_flow import RegisterFlow, RegistrationError

load_dotenv()

# 持有 flow，防止 GC；且永不在正常路径 close
_live_flows: list[RegisterFlow] = []


def _run_once(proxy: str):
    flow = RegisterFlow(proxy=proxy)
    _live_flows.append(flow)
    try:
        result = flow.register_one()
    except RegistrationError as exc:
        print(f"[-] 注册失败: {str(exc)[:240]}")
        return None, str(exc)
    except Exception as exc:
        print(f"[-] 异常: {str(exc)[:240]}")
        return None, str(exc)

    return result, ""


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ChatGPT 注册 + Sub2API 导入（浏览器保活，不自动关闭）"
    )
    p.add_argument(
        "-w",
        "--workers",
        type=int,
        default=None,
        help="忽略：保活模式固定串行 1",
    )
    p.add_argument("-n", "--total", type=int, default=None, help="数量")
    p.add_argument("--yes", action="store_true", help="非交互")
    return p.parse_args()


def _resolve_int(
    cli_value: int | None,
    env_name: str,
    default: int,
    *,
    non_interactive: bool,
    prompt: str,
) -> int:
    if cli_value is not None:
        return max(1, cli_value)
    env_raw = (os.getenv(env_name) or "").strip()
    if env_raw:
        try:
            return max(1, int(env_raw))
        except ValueError:
            pass
    if non_interactive or not os.isatty(0):
        return default
    try:
        return max(1, int(input(prompt).strip() or str(default)))
    except Exception:
        return default


def _should_hold_browsers(*, non_interactive: bool) -> bool:
    """是否在成功后挂起进程保活浏览器。

    Why: 本机调试常要 hold；VDS 无值守应 BROWSER_HOLD=0 成功即退出。
    默认：有 TTY 且未显式关闭 → hold；--yes/无 TTY → 不 hold。
    """
    raw = (os.getenv("BROWSER_HOLD") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return not non_interactive


def _hold_browsers() -> None:
    """进程保活：不 close 浏览器，直到 Ctrl+C。"""
    print()
    print("=" * 60)
    print("[*] 浏览器保持打开（ChatGPT 登录页 + Sub2API 等 tab）")
    print("[*] 永不自动关闭。按 Ctrl+C 结束进程。")
    print("[*] VDS 无值守请设 BROWSER_HOLD=0")
    print("=" * 60)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[*] 收到 Ctrl+C：进程退出（浏览器随进程结束）")


def main() -> None:
    args = _parse_args()
    non_interactive = bool(args.yes or not os.isatty(0))
    hold = _should_hold_browsers(non_interactive=non_interactive)

    print("=" * 60)
    print("ChatGPT 注册 + Sub2API 导入（浏览器保活）")
    print("=" * 60)
    print("[*] ChatGPT 主 tab 保活；Sub2API / OAuth 另开 tab")
    proxy = os.getenv("PROXY", "").strip()
    headless = (os.getenv("BROWSER_HEADLESS") or "0").strip()
    print(f"[*] PROXY={'set' if proxy else 'none'} BROWSER_HEADLESS={headless}")
    print(f"[*] BROWSER_HOLD={'1' if hold else '0'}")
    print(
        f"[*] SUB2API_BASE_URL="
        f"{(os.getenv('SUB2API_BASE_URL') or 'https://api4kimi8.org').rstrip('/')}"
    )

    total = _resolve_int(
        args.total,
        "GPT_TOTAL",
        1,
        non_interactive=non_interactive,
        prompt="注册数量 (默认1): ",
    )
    if args.workers and args.workers > 1:
        print("[!] 保活模式强制串行 workers=1（忽略 -w）")

    os.makedirs("keys", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"keys/gpt_{ts}_{total}.txt"
    accounts_file = f"keys/gpt_{ts}_{total}_accounts.txt"
    start_time = time.time()

    print(f"[*] 串行目标 {total} 个")
    print(f"[*] 账号表: {accounts_file}")

    success = 0
    for i in range(total):
        print(f"\n>>> 第 {i + 1}/{total} 次 <<<")
        result, err = _run_once(proxy)
        if result is None:
            # 失败也不关已有浏览器；继续下一轮会再开新浏览器
            continue
        try:
            token = result.access_token or "no-token"
            line = format_account_record(result.email, result.password, token)
            with open(accounts_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if result.access_token:
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(result.access_token + "\n")
        except Exception as write_err:
            print(f"[-] 写入失败: {write_err}")
            continue
        success += 1
        avg = (time.time() - start_time) / max(success, 1)
        flag = "imported" if result.imported else "registered"
        print(f"[✓] 成功 {success}/{total} | {result.email} | {flag} | 平均: {avg:.1f}s")

    print(f"\n[*] 本轮完成: 成功 {success}/{total}")
    if _live_flows and hold:
        _hold_browsers()
    elif _live_flows:
        print("[*] BROWSER_HOLD=0：保留浏览器进程句柄至退出，不挂起等待")
        print("[*] 进程即将结束（浏览器会随进程关闭）")
    else:
        print("[*] 无存活浏览器，直接退出")


if __name__ == "__main__":
    # 忽略管道关闭等，避免误杀保活
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except Exception:
        pass
    main()
