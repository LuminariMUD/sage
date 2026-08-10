"""Tests for append-only semantic-audit checkpoint persistence."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.graphiti.semantic_audit_store import (
    SemanticAuditRepository,
    entity_stage_quality_summary,
    semantic_audit_fingerprint,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": NOW.isoformat(),
        "status": "clean",
        "grounding_policy": {"normalization": "unicode_casefold_whitespace_v1"},
        "review_categories": [],
        "counts": {"graph_entities": 2},
        "rates_percent": {"literal_policy_projected_entity_retention": 100.0},
        "evidence": {"findings": [], "entity_observations": []},
        "entity_stage_quality": {
            "schema_version": 1,
            "status": "available",
            "run": {
                "id": uuid4(),
                "state": "stopped",
                "sync_profile_fingerprint": "sync:test",
                "started_at": NOW,
            },
            "evidence": {
                "extraction_attempts": 2,
                "reported_attempts": 2,
                "missing_attempts": 0,
                "coverage_percent": 100.0,
                "policies": ["strict_v1", "observe_v1"],
            },
            "anomalous_attempts": 0,
            "counts": {"dedupe_missing": 0, "summary_missing": 0},
        },
    }


def test_fingerprint_identifies_a_checkpoint_not_only_equal_graph_state():
    report = _report()
    run_id = uuid4()
    baseline = semantic_audit_fingerprint(report, run_id=run_id)
    later = deepcopy(report)
    later["generated_at"] = (NOW + timedelta(minutes=5)).isoformat()

    assert semantic_audit_fingerprint(later, run_id=run_id) != baseline
    assert semantic_audit_fingerprint(report, run_id=uuid4()) != baseline
    changed_stage = deepcopy(report)
    changed_stage["entity_stage_quality"]["anomalous_attempts"] = 1
    assert semantic_audit_fingerprint(changed_stage, run_id=run_id) != baseline


def test_stage_summary_is_content_free_json_safe_and_deterministic():
    report = _report()
    summary = entity_stage_quality_summary(report)

    assert summary["run"] == {
        "id": str(report["entity_stage_quality"]["run"]["id"]),
        "state": "stopped",
        "sync_profile_fingerprint": "sync:test",
    }
    assert summary["evidence"]["policies"] == ["observe_v1", "strict_v1"]
    assert "started_at" not in summary["run"]
    json.dumps(summary, sort_keys=True)


class _Connection:
    def __init__(self):
        self.snapshot_id = uuid4()
        self.fetchval_calls: list[tuple[str, tuple[object, ...]]] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchval(self, query: str, *args):
        self.fetchval_calls.append((query, args))
        if len(self.fetchval_calls) == 1:
            return self.snapshot_id
        return None

    async def execute(self, query: str, *args):
        raise AssertionError("Empty audit evidence should not insert child rows")

    async def fetch(self, query: str, *args):
        raise AssertionError("A first snapshot has no transition query")


class _Postgres:
    def __init__(self, connection: _Connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def test_persist_records_stage_summary_and_run_scoped_fingerprint():
    report = _report()
    run_id = uuid4()
    connection = _Connection()

    result = await SemanticAuditRepository(_Postgres(connection)).persist(
        report,
        run_id=run_id,
    )

    insert_query, args = connection.fetchval_calls[0]
    assert "entity_stage_quality" in insert_query
    assert args[0] == run_id
    assert args[1] == semantic_audit_fingerprint(report, run_id=run_id)
    assert json.loads(args[6]) == entity_stage_quality_summary(report)
    assert result["snapshot_id"] == connection.snapshot_id
    assert result["created"] is True
