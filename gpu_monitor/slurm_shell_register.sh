#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH:-}"
PYTHON_BIN="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
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
