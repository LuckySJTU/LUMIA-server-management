#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH:-}"
PYTHON_BIN="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"

if [[ -x /usr/local/bin/get_real_gpu_id ]]; then
    eval "$(/usr/local/bin/get_real_gpu_id)"
fi

"${PYTHON_BIN}" -m gpu_monitor.node_agent emit-finish-event
