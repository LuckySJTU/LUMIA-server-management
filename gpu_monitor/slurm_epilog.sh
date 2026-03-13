#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH:-}"
PYTHON_BIN="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"
export PYTHON_BIN

# GPU 映射注销不要放在 Epilog 中。
# 在启用 task/cgroup 的集群上，请改用 TaskEpilog 调用 slurm_task_epilog.sh。
exit 0
