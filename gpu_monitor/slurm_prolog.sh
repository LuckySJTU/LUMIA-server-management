#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH:-}"
if [[ -r /etc/gpu-monitor/agent.env ]]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/gpu-monitor/agent.env
    set +a
fi
PYTHON_BIN="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"
export PYTHON_BIN
export GPU_MONITOR_NODE_NAME="${GPU_MONITOR_NODE_NAME:-$(hostname -s)}"
export GPU_MONITOR_NODE_DB="${GPU_MONITOR_NODE_DB:-/var/lib/gpu-monitor/node-agent.db}"
export GPU_MONITOR_TASK_EVENT_DIR="${GPU_MONITOR_TASK_EVENT_DIR:-/var/lib/gpu-monitor/events}"

# 这里用于捕获 allocation 级别事件，例如纯 salloc 占卡但尚未启动 task 的场景。
"${PYTHON_BIN}" -m gpu_monitor.node_agent emit-alloc-register-event
