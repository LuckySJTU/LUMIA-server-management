#!/usr/bin/env bash
set -uo pipefail

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
STEP_MARKER_PATH="${GPU_MONITOR_TASK_EVENT_DIR}/gpu-monitor-step-active-${SLURM_JOB_ID:-unknown}-${SLURM_STEP_ID:-batch}.marker"

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    exit 0
fi

# TaskEpilog 负责 task 级别的关闭事件。
# 如果监控脚本失败，不应影响 Slurm 作业本身收尾。
rm -f "${STEP_MARKER_PATH}"
if ! "${PYTHON_BIN}" -m gpu_monitor.node_agent emit-finish-event; then
    echo "gpu_monitor TaskEpilog finish failed: job_id=${SLURM_JOB_ID} step_id=${SLURM_STEP_ID:-batch}" >&2
fi

exit 0
