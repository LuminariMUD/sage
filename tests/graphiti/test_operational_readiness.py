"""Tests for bounded operational readiness and deterministic alerts."""

from datetime import UTC, datetime

import pytest

from src.graphiti.operational_readiness import (
    OperationalThresholds,
    build_operational_readiness,
)


def _components() -> dict[str, object]:
    return {
        "configuration": {"graphiti_text": {"provider": "ollama"}},
        "configured_sync_profile": "sync:current",
        "sync_snapshot": {
            "counts": {
                "pending": 0,
                "leased": 0,
                "retry_wait": 0,
                "quarantined": 0,
                "synced": 3,
            },
            "total": 3,
            "eligible": 0,
            "expired_leases": 0,
            "job_attempts": 3,
            "ledger": {
                "attempts": 3,
                "completed_attempts": 3,
                "provider_calls": 3,
                "completed_provider_calls": 3,
            },
            "active_run": None,
        },
        "run_summary": {"schema_version": 1, "status": "no_runs", "run": None},
        "relationship_quality": {
            "schema_version": 1,
            "status": "no_runs",
            "run": None,
            "episode_text": "must-not-survive",
        },
        "graph_audit": {
            "schema_version": 1,
            "status": "clean",
            "state_source": "graph_sync_jobs",
            "counts": {"drift_findings": 0, "postgres_total": 3, "lifecycle": {}},
            "metadata_coverage": {"job_source_fingerprint": 3},
            "drift": {},
        },
        "embedding_preflight": {
            "schema_version": 1,
            "status": "ready",
            "scope": "episodes",
            "spaces": [
                {
                    "semantic_index": "episodes",
                    "physical_space": "episodes.embedding",
                    "status": "ready",
                    "ready": True,
                    "configured_profile": {"fingerprint": "embedding:current"},
                    "metadata": {"profile_fingerprint": "embedding:current"},
                    "physical": {
                        "dimensions": 768,
                        "total_rows": 3,
                        "embedded_rows": 3,
                        "index": {"ready": True},
                    },
                    "findings": [],
                }
            ],
        },
    }


def test_clean_components_produce_ready_content_free_report():
    report = build_operational_readiness(
        **_components(),
        generated_at=datetime(2026, 8, 7, tzinfo=UTC),
    )

    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["alerts"] == {"critical": 0, "warning": 0, "items": []}
    assert report["generated_at"] == "2026-08-07T00:00:00+00:00"
    assert "must-not-survive" not in repr(report)


def test_operational_alerts_cover_growth_leases_profiles_retries_and_provider_failures():
    components = _components()
    components["sync_snapshot"] = {
        "counts": {"quarantined": 2, "leased": 1},
        "total": 3,
        "eligible": 0,
        "expired_leases": 1,
        "job_attempts": 10,
        "ledger": {},
        "active_run": {
            "id": "run-1",
            "state": "paused_systemic",
            "sync_profile_fingerprint": "sync:stale",
            "worker_id": "must-not-survive",
            "last_failure_summary": "must-not-survive",
        },
    }
    components["run_summary"] = {
        "schema_version": 1,
        "status": "available",
        "run": {
            "id": "run-1",
            "state": "paused_systemic",
            "sync_profile_fingerprint": "sync:stale",
            "worker_id": "must-not-survive",
            "last_failure_summary": "must-not-survive",
        },
        "progress": {},
        "attempts": {
            "completed_attempts": 10,
            "outcomes": {"retry_wait": 3, "quarantined": 1},
        },
        "provider_calls": {
            "candidates": [
                {
                    "provider": "ollama",
                    "model": "model-a",
                    "candidate_fingerprint": "candidate:a",
                    "reserved": 10,
                    "completed": 10,
                    "outcomes": {"failure": 3},
                    "failure_classes": {"transport": 3},
                    "latency_ms": {"p95": 50.0},
                }
            ]
        },
    }
    components["relationship_quality"] = {
        "schema_version": 1,
        "status": "available",
        "run": {"id": "run-1"},
        "evidence": {"missing_attempts": 1},
        "vocabulary": {"fingerprints": ["vocab:a", "vocab:b"], "mixed": True},
        "episode_text": "must-not-survive",
    }
    components["graph_audit"] = {
        "schema_version": 1,
        "status": "drift",
        "state_source": "graph_sync_jobs",
        "counts": {"drift_findings": 2},
        "metadata_coverage": {},
        "drift": {
            "job_sync_profile_mismatches": [{"stable_id": "secret-episode-id"}],
            "missing_neo4j_ids": ["secret-episode-id"],
        },
    }
    components["embedding_preflight"] = {
        "schema_version": 1,
        "status": "blocked",
        "scope": "episodes",
        "spaces": [
            {
                "semantic_index": "episodes",
                "status": "blocked",
                "ready": False,
                "findings": [{"code": "profile_fingerprint_mismatch", "severity": "error"}],
                "physical": {"index": {"ready": False}},
            }
        ],
    }
    baseline = _components()
    baseline_report = {
        "schema_version": 1,
        "graph_sync": {"queue": {"counts": {"quarantined": 1}}},
    }

    report = build_operational_readiness(
        **components,
        baseline_report=baseline_report,
        generated_at=datetime(2026, 8, 7, tzinfo=UTC),
    )

    codes = {alert["code"] for alert in report["alerts"]["items"]}
    assert report["status"] == "blocked"
    assert {
        "active_sync_profile_mismatch",
        "embedding_preflight_blocked",
        "embedding_profile_mismatch",
        "expired_leases_present",
        "graph_audit_drift",
        "graph_profile_mismatch",
        "quarantined_jobs_growing",
        "quarantined_jobs_present",
        "relationship_quality_evidence_incomplete",
        "relationship_vocabulary_mixed",
        "retry_storm",
        "run_paused_systemic",
        "sustained_provider_failure",
    }.issubset(codes)
    assert baseline["configured_sync_profile"] == "sync:current"
    assert "secret-episode-id" not in repr(report)
    assert "must-not-survive" not in repr(report)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"retry_storm_min_attempts": 0},
        {"retry_storm_percent": 0},
        {"provider_failure_min_calls": True},
        {"provider_failure_percent": 101},
    ),
)
def test_operational_thresholds_reject_invalid_values(kwargs):
    with pytest.raises(ValueError):
        OperationalThresholds(**kwargs)
