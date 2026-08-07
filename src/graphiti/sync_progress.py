"""Pure progress calculations for durable Graphiti synchronization runs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

from src.graphiti.sync_models import JobState, RunState

MIN_ETA_OBSERVATION_SECONDS = 30.0


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def derive_run_progress(
    *,
    job_counts: Mapping[str, int],
    run_state: str,
    started_at: datetime,
    measured_at: datetime,
    rolling_window_started_at: datetime,
    rolling_verified: int,
) -> dict[str, object]:
    """Derive bounded completion, throughput, and explicitly approximate ETA fields."""
    try:
        state = RunState(run_state)
    except ValueError as error:
        raise ValueError("Run state is invalid") from error
    started_at = _aware(started_at, "Run start")
    measured_at = _aware(measured_at, "Progress measurement")
    rolling_window_started_at = _aware(rolling_window_started_at, "Rolling window start")
    if measured_at < started_at:
        raise ValueError("Progress measurement cannot precede the run")
    if not started_at <= rolling_window_started_at <= measured_at:
        raise ValueError("Rolling progress window is invalid")
    if (
        isinstance(rolling_verified, bool)
        or not isinstance(rolling_verified, int)
        or rolling_verified < 0
    ):
        raise ValueError("Rolling verified count is invalid")

    counts: dict[str, int] = {}
    for job_state in JobState:
        count = job_counts.get(job_state.value, 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Graph sync job counts must be non-negative integers")
        counts[job_state.value] = count
    unknown_states = set(job_counts).difference(counts)
    if unknown_states:
        raise ValueError("Graph sync job counts contain an unknown state")

    total_jobs = sum(counts.values())
    synced_jobs = counts[JobState.SYNCED.value]
    remaining_jobs = total_jobs - synced_jobs
    completion_percent = 100.0 if total_jobs == 0 else (synced_jobs / total_jobs) * 100
    elapsed_seconds = max(0.0, (measured_at - started_at).total_seconds())
    rolling_window_seconds = max(
        0.0,
        (measured_at - rolling_window_started_at).total_seconds(),
    )
    rolling_per_minute = (
        (rolling_verified * 60.0) / rolling_window_seconds if rolling_window_seconds > 0 else 0.0
    )

    approximate_eta_seconds: int | None = None
    if remaining_jobs == 0:
        eta_status = "complete"
        approximate_eta_seconds = 0
    elif state is RunState.PAUSED_SYSTEMIC:
        eta_status = "paused_systemic"
    elif counts[JobState.QUARANTINED.value] > 0:
        eta_status = "blocked_quarantine"
    elif state is RunState.STOPPED:
        eta_status = "stopped"
    elif rolling_window_seconds < MIN_ETA_OBSERVATION_SECONDS:
        eta_status = "warming_up"
    elif rolling_per_minute <= 0:
        eta_status = "insufficient_progress"
    else:
        eta_status = "available"
        approximate_eta_seconds = math.ceil(remaining_jobs * 60.0 / rolling_per_minute)

    return {
        "job_counts": counts,
        "total_jobs": total_jobs,
        "synced_jobs": synced_jobs,
        "remaining_jobs": remaining_jobs,
        "completion_percent": round(completion_percent, 3),
        "run_elapsed_seconds": round(elapsed_seconds, 3),
        "rolling_window_seconds": round(rolling_window_seconds, 3),
        "rolling_verified": rolling_verified,
        "rolling_verified_per_minute": round(rolling_per_minute, 3),
        "approximate_eta_seconds": approximate_eta_seconds,
        "eta_status": eta_status,
    }
