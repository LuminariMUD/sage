"""Unit contracts for durable graph-sync completion, throughput, and ETA."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.graphiti.sync_progress import derive_run_progress

STARTED = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def _counts(**overrides: int) -> dict[str, int]:
    counts = {
        "pending": 0,
        "leased": 0,
        "retry_wait": 0,
        "quarantined": 0,
        "synced": 0,
    }
    counts.update(overrides)
    return counts


def test_progress_derives_profile_completion_rolling_rate_and_eta():
    measured = STARTED + timedelta(minutes=5)

    progress = derive_run_progress(
        job_counts=_counts(pending=2, synced=8),
        run_state="running",
        started_at=STARTED,
        measured_at=measured,
        rolling_window_started_at=STARTED,
        rolling_verified=5,
    )

    assert progress == {
        "job_counts": _counts(pending=2, synced=8),
        "total_jobs": 10,
        "synced_jobs": 8,
        "remaining_jobs": 2,
        "completion_percent": 80.0,
        "run_elapsed_seconds": 300.0,
        "rolling_window_seconds": 300.0,
        "rolling_verified": 5,
        "rolling_verified_per_minute": 1.0,
        "approximate_eta_seconds": 120,
        "eta_status": "available",
    }


@pytest.mark.parametrize(
    ("run_state", "counts", "rolling_verified", "eta_status", "eta_seconds"),
    (
        ("paused_systemic", _counts(pending=2), 2, "paused_systemic", None),
        ("running", _counts(pending=1, quarantined=1), 2, "blocked_quarantine", None),
        ("stopped", _counts(pending=2), 2, "stopped", None),
        ("running", _counts(pending=2), 0, "insufficient_progress", None),
        ("stopped", _counts(synced=2), 0, "complete", 0),
    ),
)
def test_eta_status_explains_why_an_estimate_is_unavailable(
    run_state,
    counts,
    rolling_verified,
    eta_status,
    eta_seconds,
):
    progress = derive_run_progress(
        job_counts=counts,
        run_state=run_state,
        started_at=STARTED,
        measured_at=STARTED + timedelta(minutes=1),
        rolling_window_started_at=STARTED,
        rolling_verified=rolling_verified,
    )

    assert progress["eta_status"] == eta_status
    assert progress["approximate_eta_seconds"] == eta_seconds


def test_eta_waits_for_a_minimum_observation_window():
    progress = derive_run_progress(
        job_counts=_counts(pending=2, synced=1),
        run_state="running",
        started_at=STARTED,
        measured_at=STARTED + timedelta(seconds=10),
        rolling_window_started_at=STARTED,
        rolling_verified=1,
    )

    assert progress["eta_status"] == "warming_up"
    assert progress["approximate_eta_seconds"] is None


@pytest.mark.parametrize(
    "kwargs",
    (
        {"job_counts": _counts(pending=-1)},
        {"job_counts": {**_counts(), "unknown": 1}},
        {"rolling_verified": -1},
        {"measured_at": STARTED - timedelta(seconds=1)},
        {"rolling_window_started_at": STARTED - timedelta(seconds=1)},
    ),
)
def test_progress_rejects_invalid_or_ambiguous_inputs(kwargs):
    arguments = {
        "job_counts": _counts(pending=1),
        "run_state": "running",
        "started_at": STARTED,
        "measured_at": STARTED + timedelta(minutes=1),
        "rolling_window_started_at": STARTED,
        "rolling_verified": 0,
    }
    arguments.update(kwargs)

    with pytest.raises(ValueError):
        derive_run_progress(**arguments)
