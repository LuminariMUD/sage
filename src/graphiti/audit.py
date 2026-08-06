"""Pure reconciliation logic for PostgreSQL and Neo4j episode state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

GRAPH_SYNC_STATES = ("pending", "leased", "retry_wait", "quarantined", "synced")


def source_content_fingerprint(text: str) -> str:
    """Return the versioned digest used to identify an episode content revision."""
    digest = sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:v1:{digest}"


def _string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _sorted_records(records: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: tuple(str(item.get(key, "")) for key in keys))


def build_graph_audit(
    episode_rows: Sequence[Mapping[str, Any]],
    neo4j_rows: Sequence[Mapping[str, Any]],
    job_rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    expected_sync_profile: str | None = None,
    expected_embedding_profile: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic cross-store reconciliation report from query rows."""
    episodes: dict[str, dict[str, Any]] = {}
    for row in episode_rows:
        stable_id = str(row["stable_id"])
        episodes[stable_id] = {
            "graphiti_synced": bool(row.get("graphiti_synced")),
            "source_fingerprint": source_content_fingerprint(str(row.get("text") or "")),
        }

    jobs: dict[str, Mapping[str, Any]] = {}
    if job_rows is not None:
        jobs = {str(row["stable_id"]): row for row in job_rows}

    lifecycle_counts = dict.fromkeys(GRAPH_SYNC_STATES, 0)
    if job_rows is None:
        for episode in episodes.values():
            state = "synced" if episode["graphiti_synced"] else "pending"
            lifecycle_counts[state] += 1
        state_source = "legacy_projection"
        authoritative_synced_ids = {
            stable_id for stable_id, episode in episodes.items() if episode["graphiti_synced"]
        }
    else:
        for job in job_rows:
            state = str(job.get("state") or "")
            if state in lifecycle_counts:
                lifecycle_counts[state] += 1
        state_source = "graph_sync_jobs"
        authoritative_synced_ids = {
            stable_id
            for stable_id, job in jobs.items()
            if stable_id in episodes and job.get("state") == "synced"
        }

    populated_nodes: list[dict[str, Any]] = []
    null_stable_id_nodes: list[dict[str, Any]] = []
    for row in neo4j_rows:
        stable_id = _string(row.get("stable_id"))
        node = {
            "stable_id": stable_id,
            "source_description": _string(row.get("source_description")),
            "source_fingerprint": _string(row.get("source_fingerprint")),
            "sync_profile_fingerprint": _string(row.get("sync_profile_fingerprint")),
            "embedding_profile_fingerprint": _string(row.get("embedding_profile_fingerprint")),
        }
        if stable_id is None or not stable_id.strip():
            null_stable_id_nodes.append(node)
        else:
            populated_nodes.append(node)

    stable_id_counts = Counter(node["stable_id"] for node in populated_nodes)
    neo4j_ids = set(stable_id_counts)
    episode_ids = set(episodes)

    duplicate_stable_ids = [
        {"stable_id": stable_id, "count": count}
        for stable_id, count in sorted(stable_id_counts.items())
        if count > 1
    ]
    missing_neo4j_ids = sorted(authoritative_synced_ids - neo4j_ids)
    unexpected_neo4j_ids = sorted(neo4j_ids - episode_ids)
    neo4j_present_for_non_synced_jobs = sorted((neo4j_ids & episode_ids) - authoritative_synced_ids)

    source_description_mismatches = []
    source_fingerprint_mismatches = []
    sync_profile_mismatches = []
    embedding_profile_mismatches = []
    fingerprinted_nodes = 0
    sync_profiled_nodes = 0
    embedding_profiled_nodes = 0

    for node in populated_nodes:
        stable_id = node["stable_id"]
        if stable_id not in episode_ids:
            continue

        expected_description = f"episode_{stable_id}"
        if node["source_description"] != expected_description:
            source_description_mismatches.append(
                {
                    "stable_id": stable_id,
                    "expected": expected_description,
                    "actual": node["source_description"],
                }
            )

        node_source_fingerprint = node["source_fingerprint"]
        if node_source_fingerprint is not None:
            fingerprinted_nodes += 1
            expected_fingerprint = episodes[stable_id]["source_fingerprint"]
            if node_source_fingerprint != expected_fingerprint:
                source_fingerprint_mismatches.append(
                    {
                        "stable_id": stable_id,
                        "expected": expected_fingerprint,
                        "actual": node_source_fingerprint,
                    }
                )

        node_sync_profile = node["sync_profile_fingerprint"]
        if node_sync_profile is not None:
            sync_profiled_nodes += 1
            if expected_sync_profile and node_sync_profile != expected_sync_profile:
                sync_profile_mismatches.append(
                    {
                        "stable_id": stable_id,
                        "expected": expected_sync_profile,
                        "actual": node_sync_profile,
                    }
                )

        node_embedding_profile = node["embedding_profile_fingerprint"]
        if node_embedding_profile is not None:
            embedding_profiled_nodes += 1
            if expected_embedding_profile and node_embedding_profile != expected_embedding_profile:
                embedding_profile_mismatches.append(
                    {
                        "stable_id": stable_id,
                        "expected": expected_embedding_profile,
                        "actual": node_embedding_profile,
                    }
                )

    incorrectly_synchronized_jobs = []
    stale_job_source_fingerprints = []
    if job_rows is not None:
        for stable_id in sorted(set(jobs) - set(episodes)):
            incorrectly_synchronized_jobs.append(
                {"stable_id": stable_id, "reason": "job_without_source_episode"}
            )

        for stable_id, episode in episodes.items():
            job = jobs.get(stable_id)
            if job is None:
                incorrectly_synchronized_jobs.append(
                    {"stable_id": stable_id, "reason": "missing_job"}
                )
                continue

            state = str(job.get("state") or "")
            legacy_synced = episode["graphiti_synced"]
            if state not in GRAPH_SYNC_STATES:
                incorrectly_synchronized_jobs.append(
                    {"stable_id": stable_id, "reason": "invalid_job_state"}
                )
            if state == "synced" and not legacy_synced:
                incorrectly_synchronized_jobs.append(
                    {"stable_id": stable_id, "reason": "synced_job_legacy_flag_false"}
                )
            elif state != "synced" and legacy_synced:
                incorrectly_synchronized_jobs.append(
                    {"stable_id": stable_id, "reason": "non_synced_job_legacy_flag_true"}
                )

            if state == "synced" and job.get("verified_at") is None:
                incorrectly_synchronized_jobs.append(
                    {"stable_id": stable_id, "reason": "synced_job_missing_verified_at"}
                )

            desired_fingerprint = _string(job.get("desired_source_fingerprint"))
            if desired_fingerprint != episode["source_fingerprint"]:
                stale_job_source_fingerprints.append(
                    {
                        "stable_id": stable_id,
                        "expected": episode["source_fingerprint"],
                        "actual": desired_fingerprint,
                    }
                )

    drift = {
        "missing_neo4j_ids": missing_neo4j_ids,
        "unexpected_neo4j_ids": unexpected_neo4j_ids,
        "duplicate_stable_ids": duplicate_stable_ids,
        "null_stable_id_count": len(null_stable_id_nodes),
        "source_description_mismatches": _sorted_records(
            source_description_mismatches, "stable_id", "actual"
        ),
        "neo4j_present_for_non_synced_jobs": neo4j_present_for_non_synced_jobs,
        "incorrectly_synchronized_jobs": _sorted_records(
            incorrectly_synchronized_jobs, "stable_id", "reason"
        ),
        "source_fingerprint_mismatches": _sorted_records(
            source_fingerprint_mismatches, "stable_id"
        ),
        "stale_job_source_fingerprints": _sorted_records(
            stale_job_source_fingerprints, "stable_id"
        ),
        "sync_profile_mismatches": _sorted_records(sync_profile_mismatches, "stable_id"),
        "embedding_profile_mismatches": _sorted_records(embedding_profile_mismatches, "stable_id"),
    }
    drift_count = sum(value if isinstance(value, int) else len(value) for value in drift.values())

    timestamp = generated_at or datetime.now(UTC)
    return {
        "schema_version": 1,
        "generated_at": timestamp.isoformat(),
        "status": "clean" if drift_count == 0 else "drift",
        "state_source": state_source,
        "counts": {
            "postgres_total": len(episodes),
            "postgres_synced": len(authoritative_synced_ids),
            "postgres_non_synced": len(episodes) - len(authoritative_synced_ids),
            "neo4j_total": len(neo4j_rows),
            "neo4j_populated_stable_ids": len(populated_nodes),
            "neo4j_distinct_stable_ids": len(neo4j_ids),
            "lifecycle": lifecycle_counts,
            "drift_findings": drift_count,
        },
        "metadata_coverage": {
            "source_fingerprint": fingerprinted_nodes,
            "sync_profile_fingerprint": sync_profiled_nodes,
            "embedding_profile_fingerprint": embedding_profiled_nodes,
        },
        "drift": drift,
    }
