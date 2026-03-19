from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import shutil
import sqlite3
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import requests

from gpu_monitor.shared import NodeConfig, utcnow

try:
    import pynvml
except ImportError:  # pragma: no cover
    pynvml = None


LOGGER = logging.getLogger("gpu_monitor.node_agent")
AGENT_VERSION = "1.0.0"


def _parse_gpu_index_list(raw_value: str) -> list[int]:
    indices: list[int] = []
    for token in raw_value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_str, end_str = token.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            indices.extend(range(start, end + 1))
            continue
        indices.append(int(token))
    return indices


def _resolve_real_gpu_ids() -> str:
    if os.getenv("SLURM_REAL_GPUS"):
        return os.environ["SLURM_REAL_GPUS"]
    helper_path = "/usr/local/bin/get_real_gpu_id"
    if not os.path.exists(helper_path):
        return ""
    try:
        output = subprocess.check_output([helper_path], text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        LOGGER.exception("failed to execute %s", helper_path)
        return ""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("SLURM_REAL_GPUS="):
            return line.split("=", 1)[1]
    return ""


class NVMLProvider:
    def __init__(self) -> None:
        self.available = False
        self.index_to_uuid: dict[int, str] = {}
        self.uuid_to_index: dict[str, int] = {}
        self._init()

    def _init(self) -> None:
        if pynvml is None:
            LOGGER.warning("pynvml is not installed; sampling will be disabled")
            return
        pynvml.nvmlInit()
        self.available = True
        count = pynvml.nvmlDeviceGetCount()
        for index in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            uuid = pynvml.nvmlDeviceGetUUID(handle)
            if isinstance(uuid, bytes):
                uuid = uuid.decode()
            self.index_to_uuid[index] = uuid
            self.uuid_to_index[uuid] = index

    def uuid_from_index(self, index: int) -> str | None:
        return self.index_to_uuid.get(index)

    def visible_indices(self) -> list[int]:
        return sorted(self.index_to_uuid.keys())

    def sample_gpu(self, gpu_uuid: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        handle = pynvml.nvmlDeviceGetHandleByUUID(gpu_uuid)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        gpu_index = self.uuid_to_index[gpu_uuid]
        return {
            "gpu_uuid": gpu_uuid,
            "gpu_index": gpu_index,
            "gpu_util_percent": float(util.gpu),
            "mem_used_bytes": int(memory.used),
            "mem_total_bytes": int(memory.total),
            "mem_util_percent": round((memory.used / memory.total) * 100, 2) if memory.total else 0.0,
        }


class NodeStore:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.config.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS active_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_name TEXT NOT NULL,
                job_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                uid INTEGER NOT NULL,
                node_name TEXT NOT NULL,
                gpu_uuid TEXT NOT NULL,
                gpu_index INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                last_seen_time TEXT NOT NULL,
                mapping_source TEXT NOT NULL DEFAULT 'task_register',
                state TEXT NOT NULL,
                UNIQUE(job_id, step_id, node_name, gpu_uuid)
            );

            CREATE TABLE IF NOT EXISTS sample_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                cluster_name TEXT NOT NULL,
                node_name TEXT NOT NULL,
                job_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                uid INTEGER NOT NULL,
                gpu_uuid TEXT NOT NULL,
                gpu_index INTEGER NOT NULL,
                gpu_util_percent REAL NOT NULL,
                mem_used_bytes INTEGER NOT NULL,
                mem_total_bytes INTEGER NOT NULL,
                mem_util_percent REAL NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_sample_queue_delivered ON sample_queue(delivered, ts);
            """
        )
        active_mapping_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(active_mappings)").fetchall()
        }
        if "mapping_source" not in active_mapping_columns:
            self.connection.execute(
                "ALTER TABLE active_mappings ADD COLUMN mapping_source TEXT NOT NULL DEFAULT 'task_register'"
            )
        self.connection.commit()

    def upsert_mapping(self, mapping: dict[str, Any]) -> None:
        now = utcnow().isoformat()
        self.connection.execute(
            """
            INSERT INTO active_mappings (
                cluster_name, job_id, step_id, user_name, uid, node_name, gpu_uuid, gpu_index,
                start_time, last_seen_time, mapping_source, state
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, step_id, node_name, gpu_uuid) DO UPDATE SET
                user_name=excluded.user_name,
                uid=excluded.uid,
                gpu_index=excluded.gpu_index,
                last_seen_time=excluded.last_seen_time,
                mapping_source=excluded.mapping_source,
                state=excluded.state
            """,
            (
                mapping["cluster_name"],
                mapping["job_id"],
                mapping["step_id"],
                mapping["user_name"],
                int(mapping["uid"]),
                mapping["node_name"],
                mapping["gpu_uuid"],
                int(mapping["gpu_index"]),
                mapping["start_time"],
                now,
                mapping.get("mapping_source", "task_register"),
                mapping["state"],
            ),
        )
        self.connection.commit()

    def replace_job_mappings(self, mappings: list[dict[str, Any]]) -> None:
        if not mappings:
            return
        first = mappings[0]
        desired_gpu_uuids = {mapping["gpu_uuid"] for mapping in mappings}
        self.connection.execute(
            """
            UPDATE active_mappings
            SET state = 'CLOSED', last_seen_time = ?
            WHERE job_id = ? AND step_id = ? AND node_name = ? AND state != 'CLOSED'
              AND mapping_source != 'task_register' AND gpu_uuid NOT IN ({placeholders})
            """.format(placeholders=",".join("?" for _ in desired_gpu_uuids)),
            [
                utcnow().isoformat(),
                first["job_id"],
                first["step_id"],
                first["node_name"],
                *sorted(desired_gpu_uuids),
            ],
        )
        self.connection.commit()
        for mapping in mappings:
            self.upsert_mapping(mapping)

    def mark_job_state(self, job_id: str, step_id: str, state: str) -> list[str]:
        exact_step_ids = [
            row["step_id"]
            for row in self.connection.execute(
                """
                SELECT DISTINCT step_id
                FROM active_mappings
                WHERE job_id = ? AND step_id = ? AND state != 'CLOSED'
                """,
                (job_id, step_id),
            ).fetchall()
        ]
        target_step_ids = exact_step_ids
        if not target_step_ids and state in {"ENDING", "CLOSED"}:
            target_step_ids = [
                row["step_id"]
                for row in self.connection.execute(
                    """
                    SELECT DISTINCT step_id
                    FROM active_mappings
                    WHERE job_id = ? AND state != 'CLOSED'
                    """,
                    (job_id,),
                ).fetchall()
            ]
        if not target_step_ids:
            return []
        placeholders = ",".join("?" for _ in target_step_ids)
        self.connection.execute(
            f"""
            UPDATE active_mappings
            SET state = ?, last_seen_time = ?
            WHERE job_id = ? AND step_id IN ({placeholders})
            """,
            [state, utcnow().isoformat(), job_id, *target_step_ids],
        )
        self.connection.commit()
        return sorted(set(target_step_ids))

    def close_non_task_mappings_for_job(self, job_id: str) -> list[str]:
        step_rows = self.connection.execute(
            """
            SELECT DISTINCT step_id
            FROM active_mappings
            WHERE job_id = ? AND state != 'CLOSED' AND mapping_source != 'task_register'
            """,
            (job_id,),
        ).fetchall()
        if not step_rows:
            return []
        step_ids = [row["step_id"] for row in step_rows]
        placeholders = ",".join("?" for _ in step_ids)
        self.connection.execute(
            f"""
            UPDATE active_mappings
            SET state = 'CLOSED', last_seen_time = ?
            WHERE job_id = ? AND state != 'CLOSED' AND mapping_source != 'task_register'
              AND step_id IN ({placeholders})
            """,
            [utcnow().isoformat(), job_id, *step_ids],
        )
        self.connection.commit()
        return sorted(set(step_ids))

    def has_open_task_mappings(self, job_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM active_mappings
            WHERE job_id = ? AND state != 'CLOSED' AND mapping_source = 'task_register'
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        return row is not None

    def cleanup_stale_mappings(self, stale_minutes: int) -> list[dict[str, Any]]:
        cutoff = (utcnow() - timedelta(minutes=stale_minutes)).isoformat()
        stale_rows = self.connection.execute(
            """
            SELECT job_id, step_id, node_name, user_name, uid, gpu_uuid
            FROM active_mappings
            WHERE state != 'CLOSED' AND last_seen_time < ?
            """,
            (cutoff,),
        ).fetchall()
        if not stale_rows:
            return []
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in stale_rows:
            key = (row["job_id"], row["step_id"])
            bucket = grouped.setdefault(
                key,
                {
                    "job_id": row["job_id"],
                    "step_id": row["step_id"],
                    "node_name": row["node_name"],
                    "user_name": row["user_name"],
                    "uid": int(row["uid"]),
                    "gpu_uuids": set(),
                },
            )
            bucket["gpu_uuids"].add(row["gpu_uuid"])
        self.connection.execute(
            """
            UPDATE active_mappings
            SET state = 'CLOSED'
            WHERE state != 'CLOSED' AND last_seen_time < ?
            """,
            (cutoff,),
        )
        self.connection.commit()
        return [
            {
                "job_id": value["job_id"],
                "step_id": value["step_id"],
                "node_name": value["node_name"],
                "user_name": value["user_name"],
                "uid": value["uid"],
                "gpu_count": len(value["gpu_uuids"]),
            }
            for value in grouped.values()
        ]

    def reconcile_mappings_with_active_jobs(self, active_job_ids: set[str]) -> list[dict[str, Any]]:
        open_rows = self.connection.execute(
            """
            SELECT job_id, step_id, node_name, user_name, uid, gpu_uuid
            FROM active_mappings
            WHERE state != 'CLOSED'
            """
        ).fetchall()
        if not open_rows:
            return []
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in open_rows:
            if row["job_id"] in active_job_ids:
                continue
            key = (row["job_id"], row["step_id"])
            bucket = grouped.setdefault(
                key,
                {
                    "job_id": row["job_id"],
                    "step_id": row["step_id"],
                    "node_name": row["node_name"],
                    "user_name": row["user_name"],
                    "uid": int(row["uid"]),
                    "gpu_uuids": set(),
                },
            )
            bucket["gpu_uuids"].add(row["gpu_uuid"])
        if not grouped:
            return []
        target_keys = list(grouped.keys())
        placeholders = ",".join("(?, ?)" for _ in target_keys)
        parameters: list[Any] = [utcnow().isoformat()]
        for job_id, step_id in target_keys:
            parameters.extend([job_id, step_id])
        self.connection.execute(
            f"""
            UPDATE active_mappings
            SET state = 'CLOSED', last_seen_time = ?
            WHERE state != 'CLOSED' AND (job_id, step_id) IN ({placeholders})
            """,
            parameters,
        )
        self.connection.commit()
        return [
            {
                "job_id": value["job_id"],
                "step_id": value["step_id"],
                "node_name": value["node_name"],
                "user_name": value["user_name"],
                "uid": value["uid"],
                "gpu_count": len(value["gpu_uuids"]),
            }
            for value in grouped.values()
        ]

    def get_running_mappings(self) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT *
            FROM active_mappings
            WHERE state IN ('RUNNING', 'ENDING')
            ORDER BY job_id, gpu_index
            """
        )
        return cursor.fetchall()

    def touch_running_mappings(self, mapping_ids: list[int]) -> None:
        if not mapping_ids:
            return
        placeholders = ",".join("?" for _ in mapping_ids)
        self.connection.execute(
            f"""
            UPDATE active_mappings
            SET last_seen_time = ?
            WHERE id IN ({placeholders})
            """,
            [utcnow().isoformat(), *mapping_ids],
        )
        self.connection.commit()

    def enqueue_samples(self, samples: list[dict[str, Any]]) -> None:
        self.connection.executemany(
            """
            INSERT INTO sample_queue (
                ts, cluster_name, node_name, job_id, step_id, user_name, uid, gpu_uuid, gpu_index,
                gpu_util_percent, mem_used_bytes, mem_total_bytes, mem_util_percent, delivered
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [
                (
                    sample["ts"],
                    sample["cluster_name"],
                    sample["node_name"],
                    sample["job_id"],
                    sample["step_id"],
                    sample["user_name"],
                    int(sample["uid"]),
                    sample["gpu_uuid"],
                    int(sample["gpu_index"]),
                    float(sample["gpu_util_percent"]),
                    int(sample["mem_used_bytes"]),
                    int(sample["mem_total_bytes"]),
                    float(sample["mem_util_percent"]),
                )
                for sample in samples
            ],
        )
        self.connection.commit()

    def get_pending_samples(self, batch_limit: int) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT *
            FROM sample_queue
            WHERE delivered = 0
            ORDER BY ts
            LIMIT ?
            """,
            (batch_limit,),
        )
        return cursor.fetchall()

    def mark_samples_delivered(self, sample_ids: list[int]) -> None:
        if not sample_ids:
            return
        placeholders = ",".join("?" for _ in sample_ids)
        self.connection.execute(
            f"UPDATE sample_queue SET delivered = 1 WHERE id IN ({placeholders})",
            sample_ids,
        )
        self.connection.commit()

    def purge_delivered_and_stale_queue(self) -> None:
        cutoff = (utcnow() - timedelta(hours=self.config.undelivered_retention_hours)).isoformat()
        self.connection.execute("DELETE FROM sample_queue WHERE delivered = 1")
        self.connection.execute(
            """
            DELETE FROM sample_queue
            WHERE delivered = 0 AND ts < ?
              AND id NOT IN (
                  SELECT id FROM sample_queue WHERE delivered = 0 ORDER BY ts DESC LIMIT ?
              )
            """,
            (cutoff, self.config.undelivered_max_records),
        )
        self.connection.commit()

    def process_task_event(self, event: dict[str, Any]) -> None:
        action = event.get("action")
        if action == "register_alloc":
            mappings = event.get("mappings", [])
            if not mappings:
                return
            first = mappings[0]
            if self.has_open_task_mappings(first["job_id"]):
                LOGGER.info(
                    "ignore allocation register event because task mappings already exist; job_id=%s step_id=%s",
                    first["job_id"],
                    first["step_id"],
                )
                event["skip_job_state_sync"] = True
                return
            for mapping in mappings:
                self.upsert_mapping(mapping)
            return
        if action == "register":
            mappings = event.get("mappings", [])
            if not mappings:
                return
            for mapping in mappings:
                self.upsert_mapping(mapping)
            first = mappings[0]
            closed_step_ids = self.close_non_task_mappings_for_job(first["job_id"])
            if closed_step_ids:
                event["closed_step_ids"] = closed_step_ids
            return
        if action == "register_shell":
            mappings = event.get("mappings", [])
            if not mappings:
                return
            first = mappings[0]
            if self.has_open_task_mappings(first["job_id"]):
                LOGGER.info(
                    "ignore shell register event because task mappings already exist; job_id=%s step_id=%s",
                    first["job_id"],
                    first["step_id"],
                )
                event["skip_job_state_sync"] = True
                return
            self.replace_job_mappings(mappings)
            return
        if action in {"finish", "finish_alloc"}:
            closed_step_ids = self.mark_job_state(event["job_id"], event["step_id"], event.get("state", "CLOSED"))
            if closed_step_ids:
                event["closed_step_ids"] = closed_step_ids
            return
        raise RuntimeError(f"Unsupported task event action: {action}")


def build_mapping_from_env(config: NodeConfig, provider: NVMLProvider, source_mode: str = "task") -> list[dict[str, Any]]:
    raw_real_gpus = _resolve_real_gpu_ids()
    raw_visible_gpus = os.getenv("CUDA_VISIBLE_DEVICES") or os.getenv("GPU_DEVICE_ORDINAL") or ""
    raw_slurm_gpus = os.getenv("SLURM_STEP_GPUS") or os.getenv("SLURM_JOB_GPUS") or ""

    if source_mode == "allocation":
        if not raw_slurm_gpus:
            LOGGER.warning(
                "skip allocation event because no GPU list found in SLURM_STEP_GPUS / SLURM_JOB_GPUS; "
                "job_id=%s step_id=%s",
                os.getenv("SLURM_JOB_ID", "unknown"),
                os.getenv("SLURM_STEP_ID", "batch"),
            )
            return []
        gpu_indices = _parse_gpu_index_list(raw_slurm_gpus)
        gpu_pairs = [(gpu_index, gpu_index) for gpu_index in gpu_indices]
        gpu_source = "slurm_allocation"
        mapping_source = "allocation_register"
    elif source_mode == "shell_real":
        if not raw_real_gpus:
            raise RuntimeError("No GPU list found in SLURM_REAL_GPUS for shell event")
        real_gpu_indices = _parse_gpu_index_list(raw_real_gpus)
        visible_nvml_indices = provider.visible_indices()
        if not visible_nvml_indices:
            raise RuntimeError("No NVML-visible GPUs found while SLURM_REAL_GPUS is set for shell event")
        if len(real_gpu_indices) != len(visible_nvml_indices):
            raise RuntimeError(
                "SLURM_REAL_GPUS count does not match NVML-visible GPU count for shell event; "
                f"SLURM_REAL_GPUS={raw_real_gpus} visible_nvml_indices={visible_nvml_indices}"
            )
        gpu_pairs = list(zip(real_gpu_indices, visible_nvml_indices))
        gpu_source = "shell_real"
        mapping_source = "shell_register"
    elif raw_real_gpus:
        real_gpu_indices = _parse_gpu_index_list(raw_real_gpus)
        visible_nvml_indices = provider.visible_indices()
        if not visible_nvml_indices:
            raise RuntimeError("No NVML-visible GPUs found while SLURM_REAL_GPUS is set")
        if len(real_gpu_indices) != len(visible_nvml_indices):
            raise RuntimeError(
                "SLURM_REAL_GPUS count does not match NVML-visible GPU count; "
                f"SLURM_REAL_GPUS={raw_real_gpus} visible_nvml_indices={visible_nvml_indices}"
            )
        gpu_pairs = list(zip(real_gpu_indices, visible_nvml_indices))
        gpu_source = "real"
        mapping_source = "task_register"
    elif raw_visible_gpus:
        gpu_indices = _parse_gpu_index_list(raw_visible_gpus)
        gpu_pairs = [(gpu_index, gpu_index) for gpu_index in gpu_indices]
        gpu_source = "visible"
        mapping_source = "task_register"
    elif raw_slurm_gpus:
        gpu_indices = _parse_gpu_index_list(raw_slurm_gpus)
        gpu_pairs = [(gpu_index, gpu_index) for gpu_index in gpu_indices]
        gpu_source = "slurm"
        mapping_source = "task_register"
    else:
        raise RuntimeError(
            "No GPU list found in SLURM_REAL_GPUS / CUDA_VISIBLE_DEVICES / GPU_DEVICE_ORDINAL / SLURM_STEP_GPUS / SLURM_JOB_GPUS"
        )

    start_time = utcnow().isoformat()
    job_id = os.getenv("SLURM_JOB_ID", "unknown")
    step_id = os.getenv("SLURM_STEP_ID", "batch")
    user_name = os.getenv("SLURM_JOB_USER") or os.getenv("USER") or "unknown"
    uid = os.getenv("SLURM_JOB_UID") or os.getuid()
    entries: list[dict[str, Any]] = []
    for real_gpu_index, nvml_index in gpu_pairs:
        gpu_uuid = provider.uuid_from_index(nvml_index)
        if gpu_uuid is None:
            raise RuntimeError(
                f"Cannot resolve GPU UUID for NVML index {nvml_index} from {gpu_source} list; "
                f"visible_indices={sorted(provider.index_to_uuid.keys())} "
                f"SLURM_REAL_GPUS={os.getenv('SLURM_REAL_GPUS')} "
                f"CUDA_VISIBLE_DEVICES={os.getenv('CUDA_VISIBLE_DEVICES')} "
                f"SLURM_STEP_GPUS={os.getenv('SLURM_STEP_GPUS')}"
            )
        entries.append(
            {
                "cluster_name": config.cluster_name,
                "job_id": job_id,
                "step_id": step_id,
                "user_name": user_name,
                "uid": int(uid),
                "node_name": config.node_name,
                "gpu_uuid": gpu_uuid,
                "gpu_index": real_gpu_index,
                "start_time": start_time,
                "mapping_source": mapping_source,
                "state": "RUNNING",
            }
        )
    return entries


def _write_task_event(
    config: NodeConfig,
    *,
    action: str,
    payload: dict[str, Any],
    job_id: str,
    step_id: str,
) -> Path:
    config.task_event_dir.mkdir(parents=True, exist_ok=True)
    event_path = config.task_event_dir / (
        f"gpu-monitor-event-{action}-"
        f"{job_id}-"
        f"{step_id}-"
        f"{os.getpid()}-{int(time.time() * 1000)}.json"
    )
    event_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    return event_path


def _event_sort_key(event_path: Path) -> tuple[int, str]:
    parts = event_path.stem.rsplit("-", 2)
    if len(parts) >= 2:
        try:
            return (int(parts[-1]), event_path.name)
        except ValueError:
            pass
    try:
        return (int(event_path.stat().st_mtime_ns), event_path.name)
    except FileNotFoundError:
        return (0, event_path.name)


def emit_task_event(config: NodeConfig, provider: NVMLProvider, action: str) -> Path:
    job_id = os.getenv("SLURM_JOB_ID", "unknown")
    step_id = os.getenv("SLURM_STEP_ID", "batch")
    if action == "register":
        payload: dict[str, Any] = {
            "action": "register",
            "mappings": build_mapping_from_env(config, provider),
        }
    elif action == "register_alloc":
        mappings = build_mapping_from_env(config, provider, source_mode="allocation")
        if not mappings:
            raise RuntimeError("SKIP_EVENT_NO_ALLOCATION_GPU_MAPPING")
        payload = {
            "action": "register_alloc",
            "mappings": mappings,
        }
    elif action == "register_shell":
        payload = {
            "action": "register_shell",
            "mappings": build_mapping_from_env(config, provider, source_mode="shell_real"),
        }
    elif action == "finish":
        payload = {
            "action": "finish",
            "job_id": os.getenv("SLURM_JOB_ID", "unknown"),
            "step_id": os.getenv("SLURM_STEP_ID", "batch"),
            "state": "CLOSED",
        }
    elif action == "finish_alloc":
        payload = {
            "action": "finish_alloc",
            "job_id": os.getenv("SLURM_JOB_ID", "unknown"),
            "step_id": os.getenv("SLURM_STEP_ID", "batch"),
            "state": "CLOSED",
        }
    else:
        raise RuntimeError(f"Unsupported task event action: {action}")

    return _write_task_event(
        config,
        action=action,
        payload=payload,
        job_id=job_id,
        step_id=step_id,
    )


def emit_close_event(
    config: NodeConfig,
    *,
    job_id: str,
    step_id: str,
    node_name: str,
    user_name: str,
    uid: int,
    gpu_count: int,
    source: str,
) -> Path:
    payload = {
        "action": "finish",
        "job_id": job_id,
        "step_id": step_id,
        "state": "CLOSED",
        "node_name": node_name,
        "user_name": user_name,
        "uid": uid,
        "gpu_count": gpu_count,
        "source": source,
    }
    return _write_task_event(
        config,
        action="finish",
        payload=payload,
        job_id=job_id,
        step_id=step_id,
    )


def process_task_events(config: NodeConfig, store: NodeStore) -> int:
    processed = 0
    event_paths = list(config.task_event_dir.glob("gpu-monitor-event-*.json"))
    event_paths.sort(key=_event_sort_key)
    for event_path in event_paths:
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
            store.process_task_event(event)
            _sync_job_state_event(config, event)
            event_path.unlink()
            processed += 1
        except FileNotFoundError:
            continue
        except Exception:
            LOGGER.exception("failed to process task event file %s", event_path)
    return processed


def enqueue_stale_close_events(config: NodeConfig, stale_closures: list[dict[str, Any]]) -> int:
    queued = 0
    for stale_closure in stale_closures:
        emit_close_event(
            config,
            job_id=stale_closure["job_id"],
            step_id=stale_closure["step_id"],
            node_name=stale_closure["node_name"],
            user_name=stale_closure["user_name"],
            uid=int(stale_closure["uid"]),
            gpu_count=int(stale_closure["gpu_count"]),
            source="stale_cleanup",
        )
        queued += 1
    return queued


def _fetch_node_slurm_active_job_ids(config: NodeConfig) -> set[str] | None:
    if not config.slurm_reconcile_enabled:
        return None
    command_text = config.slurm_active_jobs_command.replace("{node_name}", config.node_name)
    command = shlex.split(command_text)
    if not command:
        LOGGER.warning("skip node Slurm reconcile because GPU_MONITOR_NODE_SLURM_ACTIVE_JOBS_COMMAND is empty")
        return None
    if shutil.which(command[0]) is None:
        LOGGER.warning("skip node Slurm reconcile because command is unavailable: %s", command[0])
        return None
    try:
        output = subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=config.slurm_command_timeout_seconds,
        )
    except Exception:
        LOGGER.exception("failed to fetch node Slurm jobs using command: %s", command_text)
        return None
    return {
        line.strip()
        for line in output.splitlines()
        if line.strip()
    }


def reconcile_local_mappings_with_slurm(config: NodeConfig, store: NodeStore) -> int:
    active_job_ids = _fetch_node_slurm_active_job_ids(config)
    if active_job_ids is None:
        return 0
    slurm_closures = store.reconcile_mappings_with_active_jobs(active_job_ids)
    if not slurm_closures:
        return 0
    queued = enqueue_stale_close_events(config, slurm_closures)
    LOGGER.warning(
        "closed %s local job steps based on Slurm reconcile and queued %s close events",
        len(slurm_closures),
        queued,
    )
    return len(slurm_closures)


def _send_job_state(
    config: NodeConfig,
    *,
    job_id: str,
    step_id: str,
    state: str,
    node_name: str | None = None,
    user_name: str | None = None,
    uid: int | None = None,
    gpu_count: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "step_id": step_id,
        "state": state,
        "ts": utcnow().isoformat(),
        "node_name": node_name or config.node_name,
    }
    if user_name is not None:
        payload["user_name"] = user_name
    if uid is not None:
        payload["uid"] = uid
    if gpu_count is not None:
        payload["gpu_count"] = gpu_count
    requests.post(
        f"{config.api_base_url.rstrip('/')}/api/v1/ingest/job-state",
        json=payload,
        timeout=config.request_timeout_seconds,
        verify=config.verify_tls,
    ).raise_for_status()


def _sync_job_state_event(config: NodeConfig, event: dict[str, Any]) -> None:
    if event.get("skip_job_state_sync"):
        return
    action = event.get("action")
    if action in {"register", "register_alloc", "register_shell"}:
        mappings = event.get("mappings", [])
        if not mappings:
            return
        first = mappings[0]
        _send_job_state(
            config,
            job_id=first["job_id"],
            step_id=first["step_id"],
            state="RUNNING",
            node_name=first.get("node_name"),
            user_name=first.get("user_name"),
            uid=int(first["uid"]),
            gpu_count=len({mapping["gpu_uuid"] for mapping in mappings}),
        )
        for closed_step_id in event.get("closed_step_ids", []):
            if closed_step_id == first["step_id"]:
                continue
            _send_job_state(
                config,
                job_id=first["job_id"],
                step_id=closed_step_id,
                state="CLOSED",
                node_name=first.get("node_name"),
            )
        return
    if action in {"finish", "finish_alloc"}:
        step_ids = event.get("closed_step_ids") or [event["step_id"]]
        for step_id in step_ids:
            _send_job_state(
                config,
                job_id=event["job_id"],
                step_id=step_id,
                state=event.get("state", "CLOSED"),
            )
        return


def capture_samples(config: NodeConfig, store: NodeStore, provider: NVMLProvider) -> int:
    mappings = store.get_running_mappings()
    by_uuid: dict[str, dict[str, Any] | None] = {}
    samples: list[dict[str, Any]] = []
    sampled_mapping_ids: list[int] = []
    sample_time = utcnow().replace(second=0, microsecond=0).isoformat()
    for mapping in mappings:
        gpu_uuid = mapping["gpu_uuid"]
        if gpu_uuid not in by_uuid:
            by_uuid[gpu_uuid] = provider.sample_gpu(gpu_uuid)
        gpu_sample = by_uuid[gpu_uuid]
        if gpu_sample is None:
            continue
        sampled_mapping_ids.append(int(mapping["id"]))
        samples.append(
            {
                "ts": sample_time,
                "cluster_name": config.cluster_name,
                "node_name": config.node_name,
                "job_id": mapping["job_id"],
                "step_id": mapping["step_id"],
                "user_name": mapping["user_name"],
                "uid": mapping["uid"],
                **gpu_sample,
            }
        )
    if samples:
        store.enqueue_samples(samples)
        store.touch_running_mappings(sampled_mapping_ids)
    return len(samples)


def flush_samples(config: NodeConfig, store: NodeStore) -> tuple[int, int]:
    pending = store.get_pending_samples(config.upload_batch_limit)
    if not pending:
        return 0, 0
    payload = {
        "node_name": config.node_name,
        "batch_time": utcnow().isoformat(),
        "samples": [
            {
                key: row[key]
                for key in (
                    "ts",
                    "cluster_name",
                    "node_name",
                    "job_id",
                    "step_id",
                    "user_name",
                    "uid",
                    "gpu_uuid",
                    "gpu_index",
                    "gpu_util_percent",
                    "mem_used_bytes",
                    "mem_total_bytes",
                    "mem_util_percent",
                )
            }
            for row in pending
        ],
    }
    response = requests.post(
        f"{config.api_base_url.rstrip('/')}/api/v1/ingest/metrics",
        json=payload,
        timeout=config.request_timeout_seconds,
        verify=config.verify_tls,
    )
    response.raise_for_status()
    body = response.json()
    accepted_count = int(body.get("accepted_count", 0))
    if accepted_count:
        store.mark_samples_delivered([row["id"] for row in pending[:accepted_count]])
    store.purge_delivered_and_stale_queue()
    return accepted_count, int(body.get("rejected_count", 0))


def send_heartbeat(config: NodeConfig, store: NodeStore) -> None:
    mappings = store.get_running_mappings()
    job_pairs = {(mapping["job_id"], mapping["step_id"]) for mapping in mappings}
    gpu_uuids = {mapping["gpu_uuid"] for mapping in mappings}
    requests.post(
        f"{config.api_base_url.rstrip('/')}/api/v1/ingest/heartbeat",
        json={
            "node_name": config.node_name,
            "agent_version": AGENT_VERSION,
            "ts": utcnow().isoformat(),
            "active_job_count": len(job_pairs),
            "active_gpu_count": len(gpu_uuids),
        },
        timeout=config.request_timeout_seconds,
        verify=config.verify_tls,
    ).raise_for_status()


def run_agent(config: NodeConfig) -> None:
    provider = NVMLProvider()
    store = NodeStore(config)
    last_flush = 0.0
    last_heartbeat = 0.0
    last_slurm_reconcile = 0.0
    while True:
        started = time.time()
        try:
            event_count = process_task_events(config, store)
            if event_count:
                LOGGER.info("processed %s task events", event_count)
            if (
                config.slurm_reconcile_enabled
                and started - last_slurm_reconcile >= config.slurm_reconcile_interval_seconds
            ):
                reconcile_local_mappings_with_slurm(config, store)
                last_slurm_reconcile = started
            sample_count = capture_samples(config, store, provider)
            LOGGER.info("captured %s samples", sample_count)
            stale_closures = store.cleanup_stale_mappings(config.mapping_stale_minutes)
            if stale_closures:
                queued_stale_events = enqueue_stale_close_events(config, stale_closures)
                LOGGER.warning(
                    "closed %s stale job steps locally and queued %s close events for controller sync",
                    len(stale_closures),
                    queued_stale_events,
                )
            if started - last_flush >= config.flush_interval_seconds:
                accepted, rejected = flush_samples(config, store)
                LOGGER.info("flushed samples accepted=%s rejected=%s", accepted, rejected)
                last_flush = started
            if started - last_heartbeat >= config.heartbeat_interval_seconds:
                send_heartbeat(config, store)
                last_heartbeat = started
        except Exception:
            LOGGER.exception("node agent loop failed")
        elapsed = time.time() - started
        time.sleep(max(1, config.sample_interval_seconds - elapsed))


def cli() -> None:
    parser = argparse.ArgumentParser(description="GPU monitor node agent and Slurm mapping hooks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run-agent")
    subparsers.add_parser("register-job")
    subparsers.add_parser("finish-job")
    subparsers.add_parser("emit-register-event")
    subparsers.add_parser("emit-finish-event")
    subparsers.add_parser("emit-alloc-register-event")
    subparsers.add_parser("emit-alloc-finish-event")
    subparsers.add_parser("emit-shell-register-event")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = NodeConfig()
    store = NodeStore(config)

    if args.command == "run-agent":
        run_agent(config)
        return

    provider = NVMLProvider()
    if args.command == "register-job":
        mappings = build_mapping_from_env(config, provider)
        for mapping in mappings:
            store.upsert_mapping(mapping)
        LOGGER.info("registered %s gpu mappings", len(mappings))
        return

    if args.command == "finish-job":
        job_id = os.getenv("SLURM_JOB_ID", "unknown")
        step_id = os.getenv("SLURM_STEP_ID", "batch")
        store.mark_job_state(job_id, step_id, "ENDING")
        try:
            accepted, rejected = flush_samples(config, store)
            LOGGER.info("final flush accepted=%s rejected=%s", accepted, rejected)
        except Exception:
            LOGGER.exception("final flush failed")
        store.mark_job_state(job_id, step_id, "CLOSED")
        return

    if args.command == "emit-register-event":
        emit_task_event(config, provider, "register")
        return

    if args.command == "emit-finish-event":
        emit_task_event(config, provider, "finish")
        return

    if args.command == "emit-alloc-register-event":
        try:
            emit_task_event(config, provider, "register_alloc")
        except RuntimeError as exc:
            if str(exc) == "SKIP_EVENT_NO_ALLOCATION_GPU_MAPPING":
                LOGGER.info("skip allocation register event without GPU mapping")
                return
            raise
        return

    if args.command == "emit-alloc-finish-event":
        emit_task_event(config, provider, "finish_alloc")
        return

    if args.command == "emit-shell-register-event":
        emit_task_event(config, provider, "register_shell")


if __name__ == "__main__":
    cli()
