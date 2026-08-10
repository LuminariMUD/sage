"""Append-only persistence for content-free semantic graph audit evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from src.db.postgres import PostgresDB
from src.graphiti.semantic_audit import NORMALIZATION_POLICY


class SemanticAuditPersistenceError(RuntimeError):
    """Semantic audit evidence cannot be persisted safely."""


def entity_stage_quality_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe, content-free stage-quality checkpoint."""
    stage = report.get("entity_stage_quality")
    if not isinstance(stage, Mapping):
        return {}
    evidence = stage.get("evidence")
    counts = stage.get("counts")
    run = stage.get("run")
    safe_evidence = dict(evidence) if isinstance(evidence, Mapping) else {}
    policies = safe_evidence.get("policies")
    if isinstance(policies, list):
        safe_evidence["policies"] = sorted(str(policy) for policy in policies)
    safe_run: dict[str, Any] = {}
    if isinstance(run, Mapping):
        for key in ("id", "state", "sync_profile_fingerprint"):
            value = run.get(key)
            if value is not None:
                safe_run[key] = str(value)
    return {
        "schema_version": stage.get("schema_version"),
        "status": stage.get("status"),
        "run": safe_run,
        "evidence": safe_evidence,
        "anomalous_attempts": stage.get("anomalous_attempts"),
        "counts": dict(counts) if isinstance(counts, Mapping) else {},
    }


def semantic_audit_fingerprint(
    report: Mapping[str, Any],
    *,
    run_id: UUID | None = None,
) -> str:
    """Fingerprint one complete content-free audit checkpoint and its provenance."""
    stable = {
        "schema_version": report.get("schema_version"),
        "generated_at": report.get("generated_at"),
        "run_id": str(run_id) if run_id is not None else None,
        "status": report.get("status"),
        "grounding_policy": report.get("grounding_policy"),
        "review_categories": report.get("review_categories"),
        "counts": report.get("counts"),
        "rates_percent": report.get("rates_percent"),
        "evidence": report.get("evidence"),
        "entity_stage_quality": entity_stage_quality_summary(report),
    }
    payload = json.dumps(
        stable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return f"semantic-audit:sha256:{hashlib.sha256(payload).hexdigest()}"


class SemanticAuditRepository:
    """Persist idempotent snapshots and derive entity transitions transactionally."""

    def __init__(self, postgres: PostgresDB):
        self.postgres = postgres

    async def persist(
        self,
        report: Mapping[str, Any],
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any]:
        evidence = report.get("evidence")
        if not isinstance(evidence, Mapping):
            raise SemanticAuditPersistenceError("Full semantic audit evidence is required")
        findings = evidence.get("findings")
        observations = evidence.get("entity_observations")
        if not isinstance(findings, list) or not isinstance(observations, list):
            raise SemanticAuditPersistenceError("Semantic audit evidence is incomplete")
        status = str(report.get("status") or "")
        if status not in {"clean", "review_required"}:
            raise SemanticAuditPersistenceError("Incomplete semantic audits cannot be persisted")
        observed_at = datetime.fromisoformat(str(report["generated_at"]))
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise SemanticAuditPersistenceError("Semantic audit timestamp is not timezone-aware")
        stage_quality = entity_stage_quality_summary(report)
        fingerprint = semantic_audit_fingerprint(report, run_id=run_id)

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                snapshot_id = await connection.fetchval(
                    """
                    INSERT INTO graph_semantic_audit_snapshots (
                        run_id,
                        report_fingerprint,
                        normalization_policy,
                        status,
                        counts,
                        rates_percent,
                        entity_stage_quality,
                        observed_at
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8)
                    ON CONFLICT (report_fingerprint) DO NOTHING
                    RETURNING id
                    """,
                    run_id,
                    fingerprint,
                    NORMALIZATION_POLICY,
                    status,
                    json.dumps(report.get("counts") or {}, sort_keys=True),
                    json.dumps(report.get("rates_percent") or {}, sort_keys=True),
                    json.dumps(stage_quality, sort_keys=True),
                    observed_at,
                )
                if snapshot_id is None:
                    snapshot_id = await connection.fetchval(
                        """
                        SELECT id
                        FROM graph_semantic_audit_snapshots
                        WHERE report_fingerprint = $1
                        """,
                        fingerprint,
                    )
                    return {
                        "snapshot_id": snapshot_id,
                        "report_fingerprint": fingerprint,
                        "created": False,
                        "finding_count": len(findings),
                        "entity_observation_count": len(observations),
                        "transition_count": 0,
                    }

                for finding in findings:
                    if not isinstance(finding, Mapping):
                        raise SemanticAuditPersistenceError("Semantic finding is malformed")
                    episode_id = finding.get("episode_id")
                    await connection.execute(
                        """
                        INSERT INTO graph_semantic_audit_findings (
                            snapshot_id,
                            category,
                            entity_uuid,
                            episode_id,
                            group_fingerprint
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        snapshot_id,
                        finding.get("category"),
                        finding.get("entity_uuid"),
                        UUID(str(episode_id)) if episode_id else None,
                        finding.get("group_fingerprint"),
                    )

                for observation in observations:
                    if not isinstance(observation, Mapping):
                        raise SemanticAuditPersistenceError("Entity observation is malformed")
                    await connection.execute(
                        """
                        INSERT INTO graph_entity_observations (
                            snapshot_id,
                            entity_uuid,
                            name_fingerprint,
                            type_fingerprint,
                            entity_types,
                            linked_episode_count
                        )
                        VALUES ($1, $2, $3, $4, $5::text[], $6)
                        """,
                        snapshot_id,
                        observation.get("entity_uuid"),
                        observation.get("name_fingerprint"),
                        observation.get("type_fingerprint"),
                        list(observation.get("entity_types") or []),
                        observation.get("linked_episode_count"),
                    )

                previous_snapshot_id = await connection.fetchval(
                    """
                    SELECT id
                    FROM graph_semantic_audit_snapshots
                    WHERE id <> $1
                    ORDER BY persisted_at DESC, id DESC
                    LIMIT 1
                    """,
                    snapshot_id,
                )
                transition_count = 0
                if previous_snapshot_id is not None:
                    transition_count = await self._record_transitions(
                        connection,
                        previous_snapshot_id=previous_snapshot_id,
                        snapshot_id=snapshot_id,
                    )
                return {
                    "snapshot_id": snapshot_id,
                    "report_fingerprint": fingerprint,
                    "created": True,
                    "finding_count": len(findings),
                    "entity_observation_count": len(observations),
                    "transition_count": transition_count,
                }

    @staticmethod
    async def _record_transitions(
        connection: Any,
        *,
        previous_snapshot_id: UUID,
        snapshot_id: UUID,
    ) -> int:
        rows = await connection.fetch(
            """
            SELECT COALESCE(previous.entity_uuid, current.entity_uuid) AS entity_uuid,
                   previous.name_fingerprint AS previous_name_fingerprint,
                   current.name_fingerprint,
                   previous.type_fingerprint AS previous_type_fingerprint,
                   current.type_fingerprint
            FROM (
                SELECT *
                FROM graph_entity_observations
                WHERE snapshot_id = $1
            ) AS previous
            FULL OUTER JOIN (
                SELECT *
                FROM graph_entity_observations
                WHERE snapshot_id = $2
            ) AS current
              ON current.entity_uuid = previous.entity_uuid
            ORDER BY entity_uuid
            """,
            previous_snapshot_id,
            snapshot_id,
        )
        transitions: list[tuple[Any, ...]] = []
        for row in rows:
            if row["previous_name_fingerprint"] is None:
                transition_types = ["created"]
            elif row["name_fingerprint"] is None:
                transition_types = ["removed"]
            else:
                transition_types = []
                if row["previous_name_fingerprint"] != row["name_fingerprint"]:
                    transition_types.append("name_changed")
                if row["previous_type_fingerprint"] != row["type_fingerprint"]:
                    transition_types.append("types_changed")
            for transition_type in transition_types:
                transitions.append(
                    (
                        previous_snapshot_id,
                        snapshot_id,
                        row["entity_uuid"],
                        transition_type,
                        row["previous_name_fingerprint"],
                        row["name_fingerprint"],
                        row["previous_type_fingerprint"],
                        row["type_fingerprint"],
                    )
                )
        if transitions:
            await connection.executemany(
                """
                INSERT INTO graph_entity_transitions (
                    previous_snapshot_id,
                    snapshot_id,
                    entity_uuid,
                    transition_type,
                    previous_name_fingerprint,
                    name_fingerprint,
                    previous_type_fingerprint,
                    type_fingerprint
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                transitions,
            )
        return len(transitions)
