#!/usr/bin/env zsh

typeset -g _GPU_MONITOR_ZSH_SCRIPT_SOURCE="${(%):-%N}"
typeset -g _GPU_MONITOR_ZSH_SCRIPT_DIR="${_GPU_MONITOR_ZSH_SCRIPT_SOURCE:A:h}"

gpu_monitor_shell_register() {
    emulate -L zsh

    export PYTHONPATH="${_GPU_MONITOR_ZSH_SCRIPT_DIR:h}:${PYTHONPATH:-}"

    if [[ -r /etc/gpu-monitor/agent.env ]]; then
        setopt allexport
        source /etc/gpu-monitor/agent.env
        unsetopt allexport
    fi

    local python_bin="${GPU_MONITOR_PYTHON:-/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3}"
    export GPU_MONITOR_NODE_NAME="${GPU_MONITOR_NODE_NAME:-$(hostname -s)}"
    export GPU_MONITOR_NODE_DB="${GPU_MONITOR_NODE_DB:-/var/lib/gpu-monitor/node-agent.db}"
    export GPU_MONITOR_TASK_EVENT_DIR="${GPU_MONITOR_TASK_EVENT_DIR:-/var/lib/gpu-monitor/events}"

    [[ -n "${SLURM_JOB_ID:-}" ]] || return 0
    [[ -o interactive ]] || return 0

    # This shell fallback is only for top-level interactive allocation shells
    # such as salloc. If a step already exists (batch/srun/task), TaskProlog
    # should be the source of truth and this script must not register again.
    [[ -z "${SLURM_STEP_ID:-}" ]] || return 0

    if [[ -n "${SLURM_STEP_GPUS:-}" ]] || [[ -n "${SLURM_PROCID:-}" ]] || [[ -n "${SLURM_LOCALID:-}" ]] || [[ -n "${SLURM_TASK_PID:-}" ]]; then
        return 0
    fi

    local step_markers=("${GPU_MONITOR_TASK_EVENT_DIR}"/gpu-monitor-step-active-"${SLURM_JOB_ID}"-*.marker(N))
    if (( ${#step_markers} > 0 )); then
        return 0
    fi

    [[ -z "${GPU_MONITOR_SHELL_REGISTERED:-}" ]] || return 0

    if [[ -x /usr/local/bin/get_real_gpu_id ]]; then
        eval "$(/usr/local/bin/get_real_gpu_id)"
    fi

    [[ -n "${SLURM_REAL_GPUS:-}" ]] || return 0

    export SLURM_REAL_GPUS
    export GPU_MONITOR_SHELL_REGISTERED=1
    "${python_bin}" -m gpu_monitor.node_agent emit-shell-register-event || true
}

gpu_monitor_shell_register "$@"
