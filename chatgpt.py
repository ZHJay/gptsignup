#!/usr/bin/env python3
# Layer: L2 流程层（CLI 边界）
# Contract: 并发注册 ChatGPT；输出 keys 下 accessToken 列表与账号表。
# Boundary: 仅编排 RegisterFlow + 文件写入；不实现协议细节。
# Why: Docker/CI 无 TTY，必须支持 --workers/--total 与环境变量非交互运行。

from __future__ import annotations

import argparse
import concurrent.futures
import os
import random
import threading
import time
from datetime import datetime

from dotenv import load_dotenv

from g.account_record import format_account_record
from g.http_session import pick_impersonate
from g.register_flow import RegisterFlow, RegistrationError

load_dotenv()

file_lock = threading.Lock()
success_count = 0
start_time = time.time()
target_count = 1
stop_event = threading.Event()
output_file = ""
accounts_file = ""
shared_impersonate = ""


def register_worker() -> None:
    time.sleep(random.uniform(0, 3))
    consecutive_fail = 0
    while not stop_event.is_set():
        flow = None
        try:
            flow = RegisterFlow(
                proxy=os.getenv("PROXY", "").strip(),
                impersonate=shared_impersonate,
            )
            result = flow.register_one()
            consecutive_fail = 0
        except RegistrationError as exc:
            msg = str(exc)
            print(f"[-] 注册失败: {msg[:160]}")
            consecutive_fail += 1
            low = msg.lower()
            # 脏号已 retire：短退避即可换下一个；429 必须长退避避免烧 IP
            if "429" in low or "too many requests" in low:
                time.sleep(min(60, 10 * consecutive_fail))
            elif "not signup-ready" in low or "login_password" in low:
                time.sleep(1)
            else:
                time.sleep(min(15, 2 * consecutive_fail))
            continue
        except Exception as exc:
            print(f"[-] 异常: {str(exc)[:160]}")
            consecutive_fail += 1
            time.sleep(min(20, 3 * consecutive_fail))
            continue
        finally:
            if flow is not None:
                flow.close()

        with file_lock:
            global success_count
            if success_count >= target_count:
                stop_event.set()
                return
            try:
                line = format_account_record(
                    result.email, result.password, result.access_token
                )
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(result.access_token + "\n")
                with open(accounts_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as write_err:
                print(f"[-] 写入失败: {write_err}")
                continue

            success_count += 1
            avg = (time.time() - start_time) / max(success_count, 1)
            token_preview = result.access_token[:18] + "..."
            print(
                f"[✓] 注册成功: {success_count}/{target_count} | "
                f"{result.email} | AT: {token_preview} | 平均: {avg:.1f}s"
            )
            if success_count >= target_count:
                stop_event.set()
                return


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ChatGPT 批量注册机")
    p.add_argument(
        "-w",
        "--workers",
        type=int,
        default=None,
        help="并发数；也可用环境变量 GPT_WORKERS",
    )
    p.add_argument(
        "-n",
        "--total",
        type=int,
        default=None,
        help="注册数量；也可用环境变量 GPT_TOTAL",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="非交互：缺失参数时用默认值，不读 stdin",
    )
    return p.parse_args()


def _resolve_int(cli_value: int | None, env_name: str, default: int, *, non_interactive: bool, prompt: str) -> int:
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


def main() -> None:
    global target_count, output_file, accounts_file, shared_impersonate, start_time

    args = _parse_args()
    non_interactive = bool(args.yes or not os.isatty(0))

    print("=" * 60)
    print("ChatGPT 注册机")
    print("=" * 60)
    print("[*] 初始化（探测 TLS 指纹）...")
    proxy = os.getenv("PROXY", "").strip()
    shared_impersonate = pick_impersonate(proxy)
    print(f"[+] impersonate={shared_impersonate}")

    workers = _resolve_int(
        args.workers,
        "GPT_WORKERS",
        3,
        non_interactive=non_interactive,
        prompt="\n并发数 (默认3): ",
    )
    total = _resolve_int(
        args.total,
        "GPT_TOTAL",
        10,
        non_interactive=non_interactive,
        prompt="注册数量 (默认10): ",
    )

    target_count = total
    workers = max(1, min(workers, target_count))

    os.makedirs("keys", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"keys/gpt_{ts}_{target_count}.txt"
    accounts_file = f"keys/gpt_{ts}_{target_count}_accounts.txt"
    start_time = time.time()

    print(f"[*] 启动 {workers} 个线程，目标 {target_count} 个")
    print(f"[*] Token 输出: {output_file}")
    print(f"[*] 账号表: {accounts_file}  (email|password|access_token)")
    print("[*] 成功后将在同一 session 请求 https://chatgpt.com/api/auth/session")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(register_worker) for _ in range(workers)]
        concurrent.futures.wait(futures)

    print(f"\n[*] 完成: 成功 {success_count}/{target_count}")


if __name__ == "__main__":
    main()
