from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Float, Integer, String, create_engine, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from gpu_monitor.shared import ControllerConfig, utcnow


class Base(DeclarativeBase):
    pass


class JobMeta(Base):
    __tablename__ = "job_meta"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    step_id: Mapped[str] = mapped_column(String(64), index=True, default="batch")
    user_name: Mapped[str] = mapped_column(String(128), index=True)
    uid: Mapped[int] = mapped_column(Integer, index=True)
    state: Mapped[str] = mapped_column(String(32), default="RUNNING", index=True)
    node_list: Mapped[list[str]] = mapped_column(JSON, default=list)
    gpu_count: Mapped[int] = mapped_column(Integer, default=0)
    submit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GpuUsageMinute(Base):
    __tablename__ = "gpu_usage_minute"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cluster_name: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    step_id: Mapped[str] = mapped_column(String(64), index=True)
    user_name: Mapped[str] = mapped_column(String(128), index=True)
    uid: Mapped[int] = mapped_column(Integer, index=True)
    node_name: Mapped[str] = mapped_column(String(128), index=True)
    gpu_uuid: Mapped[str] = mapped_column(String(128), index=True)
    gpu_index: Mapped[int] = mapped_column(Integer)
    gpu_util_percent: Mapped[float] = mapped_column(Float)
    mem_used_bytes: Mapped[int] = mapped_column(Integer)
    mem_total_bytes: Mapped[int] = mapped_column(Integer)
    mem_util_percent: Mapped[float] = mapped_column(Float)


class JobUsageHourly(Base):
    __tablename__ = "job_usage_hourly"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hour_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    user_name: Mapped[str] = mapped_column(String(128), index=True)
    gpu_count: Mapped[int] = mapped_column(Integer)
    avg_gpu_util_percent: Mapped[float] = mapped_column(Float)
    max_gpu_util_percent: Mapped[float] = mapped_column(Float)
    avg_mem_util_percent: Mapped[float] = mapped_column(Float)
    max_mem_util_percent: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)


class UserUsageHourly(Base):
    __tablename__ = "user_usage_hourly"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hour_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_name: Mapped[str] = mapped_column(String(128), index=True)
    running_job_count: Mapped[int] = mapped_column(Integer)
    allocated_gpu_count: Mapped[int] = mapped_column(Integer)
    avg_gpu_util_percent: Mapped[float] = mapped_column(Float)
    avg_mem_util_percent: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)


class NodeUsageHourly(Base):
    __tablename__ = "node_usage_hourly"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hour_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    node_name: Mapped[str] = mapped_column(String(128), index=True)
    allocated_gpu_count: Mapped[int] = mapped_column(Integer)
    avg_gpu_util_percent: Mapped[float] = mapped_column(Float)
    avg_mem_util_percent: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    level: Mapped[str] = mapped_column(String(32), index=True)
    rule_name: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(String(512))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class NodeHeartbeat(Base):
    __tablename__ = "node_heartbeat"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    agent_version: Mapped[str] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    active_job_count: Mapped[int] = mapped_column(Integer)
    active_gpu_count: Mapped[int] = mapped_column(Integer)


class MetricSampleIn(BaseModel):
    ts: datetime
    cluster_name: str
    node_name: str
    job_id: str
    step_id: str = "batch"
    user_name: str
    uid: int
    gpu_uuid: str
    gpu_index: int
    gpu_util_percent: float
    mem_used_bytes: int
    mem_total_bytes: int
    mem_util_percent: float


class MetricBatchIn(BaseModel):
    node_name: str
    batch_time: datetime
    samples: list[MetricSampleIn] = Field(default_factory=list)


class HeartbeatIn(BaseModel):
    node_name: str
    agent_version: str
    ts: datetime
    active_job_count: int
    active_gpu_count: int


config = ControllerConfig()
if config.database_url.startswith("sqlite"):
    sqlite_path = config.database_url.removeprefix("sqlite+pysqlite:///")
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
connect_args = {"check_same_thread": False} if config.database_url.startswith("sqlite") else {}
engine = create_engine(config.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_session() -> Session:
    with SessionLocal() as session:
        yield session


def _ensure_schema() -> None:
    Base.metadata.create_all(engine)


def _parse_range(range_name: str) -> tuple[datetime, datetime]:
    now = utcnow()
    if range_name == "realtime":
        return now - timedelta(minutes=15), now
    if range_name == "1d":
        return now - timedelta(days=1), now
    if range_name == "1w":
        return now - timedelta(days=7), now
    raise HTTPException(status_code=400, detail="range must be one of realtime, 1d, 1w")


def _upsert_job_meta(session: Session, sample: MetricSampleIn) -> None:
    existing = session.execute(
        select(JobMeta).where(JobMeta.job_id == sample.job_id, JobMeta.step_id == sample.step_id)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            JobMeta(
                job_id=sample.job_id,
                step_id=sample.step_id,
                user_name=sample.user_name,
                uid=sample.uid,
                state="RUNNING",
                node_list=[sample.node_name],
                gpu_count=1,
                start_time=sample.ts,
            )
        )
        return
    node_list = sorted(set(existing.node_list + [sample.node_name]))
    existing.node_list = node_list
    existing.gpu_count = max(existing.gpu_count, len(node_list))
    existing.state = "RUNNING"
    existing.end_time = None


def _serialize_user_hourly(row: UserUsageHourly) -> dict[str, Any]:
    return {
        "ts": row.hour_ts.isoformat(),
        "running_job_count": row.running_job_count,
        "allocated_gpu_count": row.allocated_gpu_count,
        "avg_gpu_util_percent": row.avg_gpu_util_percent,
        "avg_mem_util_percent": row.avg_mem_util_percent,
        "sample_count": row.sample_count,
    }


def _serialize_node_hourly(row: NodeUsageHourly) -> dict[str, Any]:
    return {
        "ts": row.hour_ts.isoformat(),
        "allocated_gpu_count": row.allocated_gpu_count,
        "avg_gpu_util_percent": row.avg_gpu_util_percent,
        "avg_mem_util_percent": row.avg_mem_util_percent,
        "sample_count": row.sample_count,
    }


def _refresh_hourly_tables(session: Session) -> None:
    now = utcnow()
    cutoff = now - timedelta(days=config.hourly_retention_days)
    source_cutoff = now - timedelta(days=7)
    session.execute(delete(JobUsageHourly).where(JobUsageHourly.hour_ts >= source_cutoff.replace(minute=0, second=0, microsecond=0)))
    session.execute(delete(UserUsageHourly).where(UserUsageHourly.hour_ts >= source_cutoff.replace(minute=0, second=0, microsecond=0)))
    session.execute(delete(NodeUsageHourly).where(NodeUsageHourly.hour_ts >= source_cutoff.replace(minute=0, second=0, microsecond=0)))

    minute_rows = session.execute(
        select(GpuUsageMinute).where(GpuUsageMinute.ts >= source_cutoff)
    ).scalars()
    job_buckets: dict[tuple[datetime, str, str], list[GpuUsageMinute]] = {}
    user_buckets: dict[tuple[datetime, str], list[GpuUsageMinute]] = {}
    node_buckets: dict[tuple[datetime, str], list[GpuUsageMinute]] = {}
    for row in minute_rows:
        hour_ts = row.ts.replace(minute=0, second=0, microsecond=0)
        job_buckets.setdefault((hour_ts, row.job_id, row.user_name), []).append(row)
        user_buckets.setdefault((hour_ts, row.user_name), []).append(row)
        node_buckets.setdefault((hour_ts, row.node_name), []).append(row)

    for (hour_ts, job_id, user_name), rows in job_buckets.items():
        session.add(
            JobUsageHourly(
                hour_ts=hour_ts,
                job_id=job_id,
                user_name=user_name,
                gpu_count=len({row.gpu_uuid for row in rows}),
                avg_gpu_util_percent=sum(row.gpu_util_percent for row in rows) / len(rows),
                max_gpu_util_percent=max(row.gpu_util_percent for row in rows),
                avg_mem_util_percent=sum(row.mem_util_percent for row in rows) / len(rows),
                max_mem_util_percent=max(row.mem_util_percent for row in rows),
                sample_count=len(rows),
            )
        )
    for (hour_ts, user_name), rows in user_buckets.items():
        session.add(
            UserUsageHourly(
                hour_ts=hour_ts,
                user_name=user_name,
                running_job_count=len({row.job_id for row in rows}),
                allocated_gpu_count=len({row.gpu_uuid for row in rows}),
                avg_gpu_util_percent=sum(row.gpu_util_percent for row in rows) / len(rows),
                avg_mem_util_percent=sum(row.mem_util_percent for row in rows) / len(rows),
                sample_count=len(rows),
            )
        )
    for (hour_ts, node_name), rows in node_buckets.items():
        session.add(
            NodeUsageHourly(
                hour_ts=hour_ts,
                node_name=node_name,
                allocated_gpu_count=len({row.gpu_uuid for row in rows}),
                avg_gpu_util_percent=sum(row.gpu_util_percent for row in rows) / len(rows),
                avg_mem_util_percent=sum(row.mem_util_percent for row in rows) / len(rows),
                sample_count=len(rows),
            )
        )
    session.execute(delete(JobUsageHourly).where(JobUsageHourly.hour_ts < cutoff))
    session.execute(delete(UserUsageHourly).where(UserUsageHourly.hour_ts < cutoff))
    session.execute(delete(NodeUsageHourly).where(NodeUsageHourly.hour_ts < cutoff))


def _upsert_alert(session: Session, entity_type: str, entity_id: str, level: str, rule_name: str, summary: str) -> None:
    existing = session.execute(
        select(Alert).where(
            Alert.entity_type == entity_type,
            Alert.entity_id == entity_id,
            Alert.rule_name == rule_name,
            Alert.status == "active",
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            Alert(
                entity_type=entity_type,
                entity_id=entity_id,
                level=level,
                rule_name=rule_name,
                summary=summary,
                start_time=utcnow(),
                last_seen_time=utcnow(),
                status="active",
            )
        )
        return
    existing.level = level
    existing.summary = summary
    existing.last_seen_time = utcnow()


def _resolve_absent_alerts(session: Session, active_keys: set[tuple[str, str, str]]) -> None:
    alerts = session.execute(select(Alert).where(Alert.status == "active")).scalars()
    now = utcnow()
    for alert in alerts:
        key = (alert.entity_type, alert.entity_id, alert.rule_name)
        if key not in active_keys:
            alert.status = "resolved"
            alert.end_time = now


def _minute_bucket(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def _group_rows_by_key_and_minute(
    rows: list[GpuUsageMinute],
    key_fn: Any,
) -> dict[str, dict[datetime, list[GpuUsageMinute]]]:
    grouped: dict[str, dict[datetime, list[GpuUsageMinute]]] = {}
    for row in rows:
        key = key_fn(row)
        grouped.setdefault(key, {}).setdefault(_minute_bucket(row.ts), []).append(row)
    return grouped


def _avg_gpu_by_minute(minute_rows: dict[datetime, list[GpuUsageMinute]]) -> tuple[int, float]:
    if not minute_rows:
        return 0, 0.0
    per_minute = [
        sum(row.gpu_util_percent for row in rows) / len(rows)
        for rows in minute_rows.values()
    ]
    return len(per_minute), sum(per_minute) / len(per_minute)


def _avg_gpu_mem_by_minute(minute_rows: dict[datetime, list[GpuUsageMinute]]) -> tuple[int, float, float]:
    if not minute_rows:
        return 0, 0.0, 0.0
    per_minute_gpu = []
    per_minute_mem = []
    for rows in minute_rows.values():
        per_minute_gpu.append(sum(row.gpu_util_percent for row in rows) / len(rows))
        per_minute_mem.append(sum(row.mem_util_percent for row in rows) / len(rows))
    count = len(per_minute_gpu)
    return count, sum(per_minute_gpu) / count, sum(per_minute_mem) / count


def _scan_alerts(session: Session) -> None:
    now = utcnow()
    active_keys: set[tuple[str, str, str]] = set()
    rows_30m = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts >= now - timedelta(minutes=30))).scalars().all()
    rows_2h = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts >= now - timedelta(hours=2))).scalars().all()
    rows_1h = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts >= now - timedelta(hours=1))).scalars().all()

    job_30m = _group_rows_by_key_and_minute(rows_30m, lambda row: row.job_id)
    job_2h = _group_rows_by_key_and_minute(rows_2h, lambda row: row.job_id)
    user_1h = _group_rows_by_key_and_minute(rows_1h, lambda row: row.user_name)
    node_1h = _group_rows_by_key_and_minute(rows_1h, lambda row: row.node_name)

    for job_id, minute_rows in job_30m.items():
        minute_count, avg_gpu, avg_mem = _avg_gpu_mem_by_minute(minute_rows)
        if minute_count >= 30:
            if avg_gpu < 10:
                active_keys.add(("job", job_id, "low_util_30m"))
                _upsert_alert(session, "job", job_id, "warning", "low_util_30m", f"job {job_id} avg gpu util {avg_gpu:.2f}% in 30m")
            if avg_mem > 60 and avg_gpu < 10:
                active_keys.add(("job", job_id, "high_mem_low_gpu"))
                _upsert_alert(session, "job", job_id, "warning", "high_mem_low_gpu", f"job {job_id} mem util {avg_mem:.2f}% but gpu util {avg_gpu:.2f}%")

    for job_id, minute_rows in job_2h.items():
        minute_count, avg_gpu = _avg_gpu_by_minute(minute_rows)
        if minute_count >= 120:
            if avg_gpu < 5:
                active_keys.add(("job", job_id, "low_util_2h"))
                _upsert_alert(session, "job", job_id, "critical", "low_util_2h", f"job {job_id} avg gpu util {avg_gpu:.2f}% in 2h")

    for user_name, minute_rows in user_1h.items():
        all_rows = [row for rows in minute_rows.values() for row in rows]
        allocated_gpu_count = len({row.gpu_uuid for row in all_rows})
        minute_count, avg_gpu = _avg_gpu_by_minute(minute_rows)
        if minute_count >= 60 and allocated_gpu_count >= 4:
            if avg_gpu < 15:
                active_keys.add(("user", user_name, "user_low_util"))
                _upsert_alert(session, "user", user_name, "warning", "user_low_util", f"user {user_name} avg gpu util {avg_gpu:.2f}% in 1h")

    for node_name, minute_rows in node_1h.items():
        minute_count = len(minute_rows)
        if minute_count >= 60:
            low_util_gpu_uuids: set[str] = set()
            for rows in minute_rows.values():
                for row in rows:
                    if row.gpu_util_percent < 10:
                        low_util_gpu_uuids.add(row.gpu_uuid)
            low_util_gpu_count = len(low_util_gpu_uuids)
            if low_util_gpu_count >= 2:
                active_keys.add(("node", node_name, "node_low_util"))
                _upsert_alert(session, "node", node_name, "warning", "node_low_util", f"node {node_name} has {low_util_gpu_count} low-util GPUs in 1h")

    _resolve_absent_alerts(session, active_keys)


def _cleanup_retention(session: Session) -> None:
    now = utcnow()
    session.execute(delete(GpuUsageMinute).where(GpuUsageMinute.ts < now - timedelta(days=config.minute_retention_days)))
    session.execute(delete(Alert).where(Alert.start_time < now - timedelta(days=config.hourly_retention_days)))


async def _worker_loop() -> None:
    while True:
        with SessionLocal() as session:
            _refresh_hourly_tables(session)
            _scan_alerts(session)
            _cleanup_retention(session)
            session.commit()
        await asyncio.sleep(config.worker_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_schema()
    task = asyncio.create_task(_worker_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="GPU Monitor API", version="1.0.0", lifespan=lifespan)


@app.post("/api/v1/ingest/metrics")
def ingest_metrics(payload: MetricBatchIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    accepted_count = 0
    rejected_count = 0
    for sample in payload.samples:
        if sample.node_name != payload.node_name:
            rejected_count += 1
            continue
        session.add(GpuUsageMinute(**sample.model_dump()))
        _upsert_job_meta(session, sample)
        accepted_count += 1
    session.commit()
    return {"accepted_count": accepted_count, "rejected_count": rejected_count, "server_time": utcnow().isoformat()}


@app.post("/api/v1/ingest/heartbeat")
def ingest_heartbeat(payload: HeartbeatIn, session: Session = Depends(get_session)) -> dict[str, str]:
    existing = session.execute(select(NodeHeartbeat).where(NodeHeartbeat.node_name == payload.node_name)).scalar_one_or_none()
    if existing is None:
        session.add(NodeHeartbeat(**payload.model_dump()))
    else:
        existing.agent_version = payload.agent_version
        existing.ts = payload.ts
        existing.active_job_count = payload.active_job_count
        existing.active_gpu_count = payload.active_gpu_count
    session.commit()
    return {"status": "ok"}


@app.get("/api/v1/overview/realtime")
def realtime_overview(session: Session = Depends(get_session)) -> dict[str, Any]:
    since = utcnow() - timedelta(minutes=15)
    rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts >= since)).scalars().all()
    if not rows:
        return {
            "running_job_count": 0,
            "allocated_gpu_count": 0,
            "avg_gpu_util_percent": 0.0,
            "avg_mem_util_percent": 0.0,
            "low_util_job_count": 0,
            "active_alert_count": 0,
        }
    job_ids = {row.job_id for row in rows}
    low_util_jobs = {
        row.job_id for row in rows if row.gpu_util_percent < 10
    }
    active_alert_count = session.scalar(select(func.count()).select_from(Alert).where(Alert.status == "active")) or 0
    return {
        "running_job_count": len(job_ids),
        "allocated_gpu_count": len({row.gpu_uuid for row in rows}),
        "avg_gpu_util_percent": round(sum(row.gpu_util_percent for row in rows) / len(rows), 2),
        "avg_mem_util_percent": round(sum(row.mem_util_percent for row in rows) / len(rows), 2),
        "low_util_job_count": len(low_util_jobs),
        "active_alert_count": int(active_alert_count),
    }


@app.get("/api/v1/jobs")
def list_jobs(
    range: str = Query("realtime"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    start, end = _parse_range(range)
    if range == "1w":
        rows = session.execute(select(JobUsageHourly).where(JobUsageHourly.hour_ts.between(start, end))).scalars().all()
        grouped: dict[str, list[JobUsageHourly]] = {}
        for row in rows:
            grouped.setdefault(row.job_id, []).append(row)
        items = [
            {
                "job_id": job_id,
                "user_name": values[-1].user_name,
                "gpu_count": max(v.gpu_count for v in values),
                "avg_gpu_util_percent": round(sum(v.avg_gpu_util_percent for v in values) / len(values), 2),
                "avg_mem_util_percent": round(sum(v.avg_mem_util_percent for v in values) / len(values), 2),
                "sample_count": sum(v.sample_count for v in values),
            }
            for job_id, values in grouped.items()
        ]
    else:
        rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts.between(start, end))).scalars().all()
        grouped: dict[str, list[GpuUsageMinute]] = {}
        for row in rows:
            grouped.setdefault(row.job_id, []).append(row)
        items = [
            {
                "job_id": job_id,
                "user_name": values[-1].user_name,
                "gpu_count": len({v.gpu_uuid for v in values}),
                "avg_gpu_util_percent": round(sum(v.gpu_util_percent for v in values) / len(values), 2),
                "avg_mem_util_percent": round(sum(v.mem_util_percent for v in values) / len(values), 2),
                "sample_count": len(values),
            }
            for job_id, values in grouped.items()
        ]
    total = len(items)
    start_index = (page - 1) * page_size
    return {"items": items[start_index:start_index + page_size], "page": page, "page_size": page_size, "total": total}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str, range: str = Query("1d"), session: Session = Depends(get_session)) -> dict[str, Any]:
    start, end = _parse_range(range)
    if range == "1w":
        rows = session.execute(select(JobUsageHourly).where(JobUsageHourly.job_id == job_id, JobUsageHourly.hour_ts.between(start, end))).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "job_id": job_id,
            "range": range,
            "series": [
                {
                    "ts": row.hour_ts.isoformat(),
                    "avg_gpu_util_percent": row.avg_gpu_util_percent,
                    "avg_mem_util_percent": row.avg_mem_util_percent,
                    "gpu_count": row.gpu_count,
                }
                for row in rows
            ],
        }
    rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.job_id == job_id, GpuUsageMinute.ts.between(start, end))).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job_id,
        "user_name": rows[-1].user_name,
        "nodes": sorted({row.node_name for row in rows}),
        "gpus": sorted({row.gpu_uuid for row in rows}),
        "range": range,
        "series": [
            {
                "ts": row.ts.isoformat(),
                "node_name": row.node_name,
                "gpu_uuid": row.gpu_uuid,
                "gpu_util_percent": row.gpu_util_percent,
                "mem_util_percent": row.mem_util_percent,
            }
            for row in rows
        ],
    }


@app.get("/api/v1/users")
def list_users(range: str = Query("realtime"), session: Session = Depends(get_session)) -> dict[str, Any]:
    start, end = _parse_range(range)
    if range == "1w":
        rows = session.execute(select(UserUsageHourly).where(UserUsageHourly.hour_ts.between(start, end))).scalars().all()
        grouped: dict[str, list[UserUsageHourly]] = {}
        for row in rows:
            grouped.setdefault(row.user_name, []).append(row)
        items = [
            {
                "user_name": user_name,
                "running_job_count": max(v.running_job_count for v in values),
                "allocated_gpu_count": max(v.allocated_gpu_count for v in values),
                "avg_gpu_util_percent": round(sum(v.avg_gpu_util_percent for v in values) / len(values), 2),
                "avg_mem_util_percent": round(sum(v.avg_mem_util_percent for v in values) / len(values), 2),
            }
            for user_name, values in grouped.items()
        ]
    else:
        rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts.between(start, end))).scalars().all()
        grouped: dict[str, list[GpuUsageMinute]] = {}
        for row in rows:
            grouped.setdefault(row.user_name, []).append(row)
        items = [
            {
                "user_name": user_name,
                "running_job_count": len({v.job_id for v in values}),
                "allocated_gpu_count": len({v.gpu_uuid for v in values}),
                "avg_gpu_util_percent": round(sum(v.gpu_util_percent for v in values) / len(values), 2),
                "avg_mem_util_percent": round(sum(v.mem_util_percent for v in values) / len(values), 2),
            }
            for user_name, values in grouped.items()
        ]
    return {"items": items, "total": len(items)}


@app.get("/api/v1/users/{user_name}")
def get_user(user_name: str, range: str = Query("1d"), session: Session = Depends(get_session)) -> dict[str, Any]:
    start, end = _parse_range(range)
    if range == "1w":
        rows = session.execute(select(UserUsageHourly).where(UserUsageHourly.user_name == user_name, UserUsageHourly.hour_ts.between(start, end))).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="user not found")
        return {"user_name": user_name, "range": range, "series": [_serialize_user_hourly(row) for row in rows]}
    rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.user_name == user_name, GpuUsageMinute.ts.between(start, end))).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="user not found")
    return {
        "user_name": user_name,
        "running_jobs": sorted({row.job_id for row in rows}),
        "nodes": sorted({row.node_name for row in rows}),
        "range": range,
        "series": [
            {
                "ts": row.ts.isoformat(),
                "job_id": row.job_id,
                "node_name": row.node_name,
                "gpu_util_percent": row.gpu_util_percent,
                "mem_util_percent": row.mem_util_percent,
            }
            for row in rows
        ],
    }


@app.get("/api/v1/nodes")
def list_nodes(range: str = Query("realtime"), session: Session = Depends(get_session)) -> dict[str, Any]:
    start, end = _parse_range(range)
    if range == "1w":
        rows = session.execute(select(NodeUsageHourly).where(NodeUsageHourly.hour_ts.between(start, end))).scalars().all()
        grouped: dict[str, list[NodeUsageHourly]] = {}
        for row in rows:
            grouped.setdefault(row.node_name, []).append(row)
        items = [
            {
                "node_name": node_name,
                "gpu_allocated": max(v.allocated_gpu_count for v in values),
                "avg_gpu_util_percent": round(sum(v.avg_gpu_util_percent for v in values) / len(values), 2),
                "avg_mem_util_percent": round(sum(v.avg_mem_util_percent for v in values) / len(values), 2),
            }
            for node_name, values in grouped.items()
        ]
    else:
        rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.ts.between(start, end))).scalars().all()
        grouped: dict[str, list[GpuUsageMinute]] = {}
        for row in rows:
            grouped.setdefault(row.node_name, []).append(row)
        items = [
            {
                "node_name": node_name,
                "gpu_allocated": len({v.gpu_uuid for v in values}),
                "avg_gpu_util_percent": round(sum(v.gpu_util_percent for v in values) / len(values), 2),
                "avg_mem_util_percent": round(sum(v.mem_util_percent for v in values) / len(values), 2),
            }
            for node_name, values in grouped.items()
        ]
    return {"items": items, "total": len(items)}


@app.get("/api/v1/nodes/{node_name}")
def get_node(node_name: str, range: str = Query("1d"), session: Session = Depends(get_session)) -> dict[str, Any]:
    start, end = _parse_range(range)
    if range == "1w":
        rows = session.execute(select(NodeUsageHourly).where(NodeUsageHourly.node_name == node_name, NodeUsageHourly.hour_ts.between(start, end))).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="node not found")
        return {"node_name": node_name, "range": range, "series": [_serialize_node_hourly(row) for row in rows]}
    rows = session.execute(select(GpuUsageMinute).where(GpuUsageMinute.node_name == node_name, GpuUsageMinute.ts.between(start, end))).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="node not found")
    return {
        "node_name": node_name,
        "active_jobs": sorted({row.job_id for row in rows}),
        "range": range,
        "series": [
            {
                "ts": row.ts.isoformat(),
                "job_id": row.job_id,
                "user_name": row.user_name,
                "gpu_uuid": row.gpu_uuid,
                "gpu_util_percent": row.gpu_util_percent,
                "mem_util_percent": row.mem_util_percent,
            }
            for row in rows
        ],
    }


@app.get("/api/v1/alerts")
def list_alerts(
    status: str = Query("active"),
    entity_type: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(Alert)
    if status:
        query = query.where(Alert.status == status)
    if entity_type:
        query = query.where(Alert.entity_type == entity_type)
    rows = session.execute(query.order_by(Alert.last_seen_time.desc())).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "level": row.level,
                "rule_name": row.rule_name,
                "summary": row.summary,
                "start_time": row.start_time.isoformat(),
                "last_seen_time": row.last_seen_time.isoformat(),
                "end_time": row.end_time.isoformat() if row.end_time else None,
                "status": row.status,
            }
            for row in rows
        ],
        "total": len(rows),
    }


def main() -> None:
    import uvicorn

    _ensure_schema()
    uvicorn.run("gpu_monitor.controller_app:app", host=config.api_host, port=config.api_port, reload=False)


if __name__ == "__main__":
    main()
