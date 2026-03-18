from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class NodeConfig:
    cluster_name: str = os.getenv("GPU_MONITOR_CLUSTER_NAME", "default-cluster")
    node_name: str = os.getenv("GPU_MONITOR_NODE_NAME", os.uname().nodename)
    db_path: Path = Path(os.getenv("GPU_MONITOR_NODE_DB", "/var/lib/gpu-monitor/node-agent.db"))
    api_base_url: str = os.getenv("GPU_MONITOR_API_BASE_URL", "http://127.0.0.1:8000")
    sample_interval_seconds: int = int(os.getenv("GPU_MONITOR_SAMPLE_INTERVAL_SECONDS", "15"))
    flush_interval_seconds: int = int(os.getenv("GPU_MONITOR_FLUSH_INTERVAL_SECONDS", "60"))
    mapping_stale_minutes: int = int(os.getenv("GPU_MONITOR_MAPPING_STALE_MINUTES", "10"))
    upload_batch_limit: int = int(os.getenv("GPU_MONITOR_UPLOAD_BATCH_LIMIT", "2000"))
    verify_tls: bool = env_bool("GPU_MONITOR_VERIFY_TLS", False)
    request_timeout_seconds: int = int(os.getenv("GPU_MONITOR_REQUEST_TIMEOUT_SECONDS", "15"))
    heartbeat_interval_seconds: int = int(os.getenv("GPU_MONITOR_HEARTBEAT_INTERVAL_SECONDS", "300"))
    task_event_dir: Path = Path(os.getenv("GPU_MONITOR_TASK_EVENT_DIR", "/tmp"))
    undelivered_retention_hours: int = int(os.getenv("GPU_MONITOR_UNDELIVERED_RETENTION_HOURS", "24"))
    undelivered_max_records: int = int(os.getenv("GPU_MONITOR_UNDELIVERED_MAX_RECORDS", "100000"))
    slurm_reconcile_enabled: bool = env_bool("GPU_MONITOR_NODE_SLURM_RECONCILE_ENABLED", True)
    slurm_reconcile_interval_seconds: int = int(os.getenv("GPU_MONITOR_NODE_SLURM_RECONCILE_INTERVAL_SECONDS", "300"))
    slurm_active_jobs_command: str = os.getenv("GPU_MONITOR_NODE_SLURM_ACTIVE_JOBS_COMMAND", "squeue -h -w {node_name} -o %A")
    slurm_command_timeout_seconds: int = int(os.getenv("GPU_MONITOR_NODE_SLURM_COMMAND_TIMEOUT_SECONDS", "15"))


@dataclass(slots=True)
class ControllerConfig:
    database_url: str = os.getenv(
        "GPU_MONITOR_DATABASE_URL",
        "sqlite+pysqlite:///./gpu_monitor/controller/gpu-monitor.db",
    )
    api_host: str = os.getenv("GPU_MONITOR_API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("GPU_MONITOR_API_PORT", "8000"))
    cluster_name: str = os.getenv("GPU_MONITOR_CLUSTER_NAME", "default-cluster")
    minute_retention_days: int = int(os.getenv("GPU_MONITOR_MINUTE_RETENTION_DAYS", "7"))
    hourly_retention_days: int = int(os.getenv("GPU_MONITOR_HOURLY_RETENTION_DAYS", "30"))
    worker_interval_seconds: int = int(os.getenv("GPU_MONITOR_WORKER_INTERVAL_SECONDS", "60"))
    enable_embedded_worker: bool = env_bool("GPU_MONITOR_ENABLE_EMBEDDED_WORKER", True)
    db_pool_size: int = int(os.getenv("GPU_MONITOR_DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("GPU_MONITOR_DB_MAX_OVERFLOW", "20"))
    db_pool_timeout_seconds: int = int(os.getenv("GPU_MONITOR_DB_POOL_TIMEOUT_SECONDS", "30"))
    db_pool_recycle_seconds: int = int(os.getenv("GPU_MONITOR_DB_POOL_RECYCLE_SECONDS", "1800"))
    slurm_reconcile_enabled: bool = env_bool("GPU_MONITOR_SLURM_RECONCILE_ENABLED", True)
    slurm_reconcile_interval_seconds: int = int(os.getenv("GPU_MONITOR_SLURM_RECONCILE_INTERVAL_SECONDS", "300"))
    slurm_active_jobs_command: str = os.getenv("GPU_MONITOR_SLURM_ACTIVE_JOBS_COMMAND", "squeue -h -o %A")
    slurm_command_timeout_seconds: int = int(os.getenv("GPU_MONITOR_SLURM_COMMAND_TIMEOUT_SECONDS", "15"))
