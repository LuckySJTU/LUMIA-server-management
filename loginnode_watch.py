#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
import time
import pwd
from pathlib import Path

try:
    import psutil
except ImportError:
    print("Please: pip install psutil", file=sys.stderr)
    sys.exit(1)

# 尝试加载 eBPF/BCC，用于按进程统计网络吞吐
HAVE_BCC = False
try:
    from bcc import BPF
    HAVE_BCC = True
except Exception:
    HAVE_BCC = False


def is_root():
    return os.geteuid() == 0


def username_of(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except Exception:
        return str(uid)


def looks_like_vscode_task(proc):
    """
    排除规则：
    - 进程的 cwd/cmdline/path 中包含 '/.vscode/'
    - 命令行中包含类似 'vscode-server' / VSCode 扩展运行路径（常见于 ~/.vscode）
    """
    patterns = ["/.vscode/", "vscode-server", "VSCode"]
    try:
        # cwd
        cwd = ""
        try:
            cwd = proc.cwd() or ""
        except Exception:
            pass
        # exe path
        exe = ""
        try:
            exe = proc.exe() or ""
        except Exception:
            pass
        # cmdline
        cmdline = " ".join(proc.cmdline()) if proc.cmdline() else ""
        hay = " ".join([cwd, exe, cmdline]).lower()
        return any(p.lower() in hay for p in patterns)
    except Exception:
        return False


def collect_ps_info(interval_sec):
    """
    返回：pid -> dict(cpu_percent=float, user=str, cmdline=str)
    """
    procs = {p.pid: p for p in psutil.process_iter(attrs=["pid", "username", "cmdline"])}

    # 先 prime 一次 cpu_percent
    for p in procs.values():
        try:
            p.cpu_percent(None)
        except Exception:
            pass

    time.sleep(interval_sec)

    out = {}
    for pid, p in procs.items():
        try:
            cpu = p.cpu_percent(None)  # 与上次调用间隔期间的平均 CPU%
            u = p.uids().real if hasattr(p, "uids") else None
            user = p.username() if p.info.get("username") is None else p.info["username"]
            if user is None and u is not None:
                user = username_of(u)
            cmdline = " ".join(p.info.get("cmdline") or p.cmdline() or []) or (p.name() or "")
            out[pid] = dict(cpu_percent=cpu, user=user, cmdline=cmdline)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue
    return out


BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <net/sock.h>

BPF_HASH(tx_bytes, u32, u64);
BPF_HASH(rx_bytes, u32, u64);

// 发送方向：tcp_sendmsg(sock *sk, msghdr *msg, size_t size)
int kprobe__tcp_sendmsg(struct pt_regs *ctx, struct sock *sk, struct msghdr *msg, size_t size) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *val, zero = 0;
    val = tx_bytes.lookup(&pid);
    if (!val) {
        tx_bytes.update(&pid, &zero);
        val = tx_bytes.lookup(&pid);
    }
    if (val) {
        __sync_fetch_and_add(val, size);
    }
    return 0;
}

// 接收方向：tcp_cleanup_rbuf(struct sock *sk, int copied)
int kprobe__tcp_cleanup_rbuf(struct pt_regs *ctx, struct sock *sk, int copied) {
    if (copied <= 0) { return 0; }
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *val, zero = 0;
    val = rx_bytes.lookup(&pid);
    if (!val) {
        rx_bytes.update(&pid, &zero);
        val = rx_bytes.lookup(&pid);
    }
    if (val) {
        __sync_fetch_and_add(val, (u64)copied);
    }
    return 0;
}
"""


def collect_net_bytes(interval_sec):
    """
    使用 eBPF 统计 interval_sec 时间窗内各 pid 的网络发送/接收字节数。
    返回：pid -> (tx_Bps, rx_Bps)
    """
    if not HAVE_BCC:
        return {}

    b = BPF(text=BPF_PROGRAM)
    # 采样窗口
    time.sleep(interval_sec)

    tx = b.get_table("tx_bytes")
    rx = b.get_table("rx_bytes")

    out = {}
    # bytes per second
    denom = float(max(interval_sec, 1e-6))
    for k, v in tx.items():
        pid = int(k.value)
        out.setdefault(pid, [0.0, 0.0])
        out[pid][0] = int(v.value) / denom  # B/s

    for k, v in rx.items():
        pid = int(k.value)
        out.setdefault(pid, [0.0, 0.0])
        out[pid][1] = int(v.value) / denom  # B/s

    # 清理探针（本函数调用后就结束）
    b.cleanup()
    return {pid: tuple(vals) for pid, vals in out.items()}


def bytes_to_mbps(Bps):
    # 8 bits per byte, 1e6 bits per Mbps
    return (Bps * 8.0) / 1_000_000.0


def main():
    parser = argparse.ArgumentParser(description="Login-node process watcher (CPU & Net per PID)")
    parser.add_argument("--interval", type=int, default=5, help="sampling window (seconds)")
    parser.add_argument("--cpu-threshold", type=float, default=100.0, help="CPU%% threshold per process")
    parser.add_argument("--net-threshold-mbps", type=float, default=10.0, help="Net threshold (either TX or RX) in Mbps")
    parser.add_argument("--topk", type=int, default=100, help="max rows to display")
    parser.add_argument("--show-all", action="store_true", help="show all rows, not only over-threshold")
    args = parser.parse_args()

    if not is_root() and HAVE_BCC:
        print("Warning: Not running as root. eBPF may fail to attach; run with sudo for full network stats.", file=sys.stderr)

    if not HAVE_BCC:
        print("[INFO] python-bcc not available -> network stats disabled (CPU-only).", file=sys.stderr)
        print("       To enable per-process net usage: apt install bpfcc-tools python3-bcc", file=sys.stderr)

    # 两个采样窗口要一致：为避免重复等待，总是以 CPU 为准采样，再把 eBPF 结果按比例合并。
    interval = max(1, int(args.interval))

    # 先并行/交错采集：先热身一次 CPU 百分比，再立即启动 eBPF 并 sleep interval，然后读取两侧结果
    # 由于 psutil.cpu_percent 需要两次调用，我们采用 collect_ps_info(interval) 直接内部 sleep。
    # 对于 eBPF，我们在调用前先启动并 sleep interval，这会与 collect_ps_info(interval) 重复等待。
    # 为避免双倍等待，策略改为：
    #   1) 先启动 eBPF -> sleep interval
    #   2) 紧接着立刻做一次短 CPU 采样（1秒），这样两个窗口接近。
    net_rates = collect_net_bytes(interval_sec=interval)
    ps_info = collect_ps_info(interval_sec=1)

    rows = []
    for pid, info in ps_info.items():
        # 过滤掉 root
        if info.get("user") in ("root", "0"):
            continue

        # 过滤 VSCode 任务
        try:
            proc = psutil.Process(pid)
            if looks_like_vscode_task(proc):
                continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            pass

        cpu = info.get("cpu_percent", 0.0)

        tx_mbps = rx_mbps = 0.0
        if HAVE_BCC:
            if pid in net_rates:
                tx_Bps, rx_Bps = net_rates[pid]
                tx_mbps = bytes_to_mbps(tx_Bps)
                rx_mbps = bytes_to_mbps(rx_Bps)

        over_cpu = cpu >= args.cpu_threshold
        over_net = HAVE_BCC and (tx_mbps >= args.net_threshold_mbps or rx_mbps >= args.net_threshold_mbps)

        if args.show_all or over_cpu or over_net:
            rows.append((
                pid,
                info.get("user", "?"),
                cpu,
                tx_mbps,
                rx_mbps,
                info.get("cmdline", "")
            ))

    # 排序：优先网络（TX+RX），再 CPU
    def sort_key(r):
        _, _, cpu, tx, rx, _ = r
        return (tx + rx, cpu)

    rows.sort(key=sort_key, reverse=True)

    # 打印表格
    from shutil import get_terminal_size
    width = get_terminal_size((120, 30)).columns
    header = f"{'PID':>7}  {'USER':<16}  {'CPU%':>6}  {'TX(Mbps)':>10}  {'RX(Mbps)':>10}  CMD"
    print(header)
    print("-" * min(width, len(header) + 80))

    count = 0
    for r in rows:
        if count >= args.topk:
            break
        pid, user, cpu, tx, rx, cmd = r
        print(f"{pid:7d}  {user:<16}  {cpu:6.1f}  {tx:10.2f}  {rx:10.2f}  {cmd}")
        count += 1

    if count == 0:
        print("(no processes over thresholds or matching filters)")

    # 友好提示
    if not HAVE_BCC:
        print("\n[NOTE] Network usage requires eBPF/BCC. Install and re-run with sudo to enable per-process TX/RX.")


if __name__ == "__main__":
    main()

