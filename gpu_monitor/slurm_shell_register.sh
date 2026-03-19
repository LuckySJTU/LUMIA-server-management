#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH:-}"
if [[ -r /etc/gpu-monitor/agent.env ]]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/gpu-monitor/agent.env
    set +a
fi
PYTHON_BIN="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"
export GPU_MONITOR_NODE_NAME="${GPU_MONITOR_NODE_NAME:-$(hostname -s)}"
export GPU_MONITOR_NODE_DB="${GPU_MONITOR_NODE_DB:-/var/lib/gpu-monitor/node-agent.db}"
export GPU_MONITOR_TASK_EVENT_DIR="${GPU_MONITOR_TASK_EVENT_DIR:-/var/lib/gpu-monitor/events}"

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    exit 0
fi

case "$-" in
    *i*) ;;
    *) exit 0 ;;
esac

# This shell fallback is only for top-level interactive allocation shells
# such as salloc. If a step already exists (batch/srun/task), TaskProlog
# should be the source of truth and this script must not register again.
if [[ -n "${SLURM_STEP_ID:-}" ]]; then
    exit 0
fi

if [[ -n "${SLURM_STEP_GPUS:-}" ]] || [[ -n "${SLURM_PROCID:-}" ]] || [[ -n "${SLURM_LOCALID:-}" ]] || [[ -n "${SLURM_TASK_PID:-}" ]]; then
    exit 0
fi

if compgen -G "${GPU_MONITOR_TASK_EVENT_DIR}/gpu-monitor-step-active-${SLURM_JOB_ID}-*.marker" > /dev/null; then
    exit 0
fi

if [[ -n "${GPU_MONITOR_SHELL_REGISTERED:-}" ]]; then
    exit 0
fi

if [[ -x /usr/local/bin/get_real_gpu_id ]]; then
    eval "$(/usr/local/bin/get_real_gpu_id)"
fi

if [[ -z "${SLURM_REAL_GPUS:-}" ]]; then
    exit 0
fi

export SLURM_REAL_GPUS

export GPU_MONITOR_SHELL_REGISTERED=1
"${PYTHON_BIN}" -m gpu_monitor.node_agent emit-shell-register-event || true
