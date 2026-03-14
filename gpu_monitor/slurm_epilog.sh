#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH:-}"
PYTHON_BIN="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"
export PYTHON_BIN

# 这里用于捕获 allocation 级别释放事件，例如纯 salloc 结束释放资源的场景。
"${PYTHON_BIN}" -m gpu_monitor.node_agent emit-alloc-finish-event
