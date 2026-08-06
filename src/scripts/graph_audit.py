#!/usr/bin/env python3
"""Read-only PostgreSQL/Neo4j graph reconciliation command."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

sys.path.insert(0, "/app")

from src.db.neo4j_db import Neo4jDB
from src.db.postgres import PostgresDB
from src.graphiti.audit import build_graph_audit

POSTGRES_EPISODE_QUERY = """
    SELECT id::text AS stable_id, text, graphiti_synced, graphiti_synced_at
    FROM episodes
    ORDER BY id
"""

POSTGRES_JOB_QUERY = """
    SELECT episode_id::text AS stable_id,
           state,
           desired_source_fingerprint,
           sync_profile_fingerprint,
           verified_source_fingerprint,
           verified_sync_profile_fingerprint,
           verified_at
    FROM graph_sync_jobs
    ORDER BY episode_id
"""

NEO4J_EPISODE_QUERY = """
    MATCH (ep:Episodic)
    RETURN ep.stable_id AS stable_id,
           ep.source_description AS source_description,
           ep.source_fingerprint AS source_fingerprint,
           ep.sync_profile_fingerprint AS sync_profile_fingerprint,
           ep.embedding_profile_fingerprint AS embedding_profile_fingerprint
    ORDER BY stable_id, source_description
"""


async def collect_graph_audit(
    postgres: PostgresDB,
    neo4j: Neo4jDB,
    *,
    expected_sync_profile: str | None = None,
    expected_embedding_profile: str | None = None,
) -> dict[str, Any]:
    """Collect both read-only snapshots and build the audit report."""
    episode_rows = await postgres.fetch(POSTGRES_EPISODE_QUERY)
    has_jobs = await postgres.fetchval("SELECT to_regclass('public.graph_sync_jobs') IS NOT NULL")
    job_rows = await postgres.fetch(POSTGRES_JOB_QUERY) if has_jobs else None
    neo4j_rows = await neo4j.execute_query(NEO4J_EPISODE_QUERY)
    return build_graph_audit(
        episode_rows,
        neo4j_rows,
        job_rows,
        expected_sync_profile=expected_sync_profile,
        expected_embedding_profile=expected_embedding_profile,
    )


def render_human(report: dict[str, Any]) -> str:
    """Render a compact, actionable audit summary."""
    counts = report["counts"]
    coverage = report["metadata_coverage"]
    drift = report["drift"]
    lines = [
        "Graph audit: " + report["status"].upper(),
        f"State source: {report['state_source']}",
        (
            "PostgreSQL: "
            f"{counts['postgres_total']} total, {counts['postgres_synced']} synced, "
            f"{counts['postgres_non_synced']} non-synced"
        ),
        (
            "Neo4j Episodic: "
            f"{counts['neo4j_total']} total, "
            f"{counts['neo4j_populated_stable_ids']} populated stable IDs, "
            f"{counts['neo4j_distinct_stable_ids']} distinct"
        ),
        "Lifecycle: " + ", ".join(f"{key}={value}" for key, value in counts["lifecycle"].items()),
        (
            "Neo4j metadata coverage: "
            f"source={coverage['source_fingerprint']}, "
            f"sync_profile={coverage['sync_profile_fingerprint']}, "
            f"embedding_profile={coverage['embedding_profile_fingerprint']}"
        ),
        (
            "Job metadata coverage: "
            f"desired_source={coverage['job_source_fingerprint']}, "
            f"verified_source={coverage['job_verified_source_fingerprint']}, "
            f"sync_profile={coverage['job_sync_profile_fingerprint']}"
        ),
        f"Drift findings: {counts['drift_findings']}",
    ]

    if report["status"] == "drift":
        for name, findings in drift.items():
            count = findings if isinstance(findings, int) else len(findings)
            if not count:
                continue
            lines.append(f"- {name}: {count}")
            if isinstance(findings, list):
                for finding in findings:
                    if isinstance(finding, str):
                        lines.append(f"  - {finding}")
                    else:
                        lines.append("  - " + json.dumps(finding, sort_keys=True))

    return "\n".join(lines)


async def run(args: argparse.Namespace) -> int:
    """Execute the audit and return its stable process exit code."""
    postgres = None
    neo4j = None
    try:
        postgres = PostgresDB(read_only=True)
        neo4j = Neo4jDB(read_only=True)
        await postgres.connect()
        await neo4j.connect()
        report = await collect_graph_audit(
            postgres,
            neo4j,
            expected_sync_profile=args.expected_sync_profile,
            expected_embedding_profile=args.expected_embedding_profile,
        )
    except Exception as error:
        incomplete = {
            "schema_version": 1,
            "status": "incomplete",
            "error_type": type(error).__name__,
            "message": "Graph audit could not complete",
        }
        if args.json:
            print(json.dumps(incomplete, indent=2, sort_keys=True))
        else:
            print(
                f"Graph audit: INCOMPLETE ({incomplete['error_type']})",
                file=sys.stderr,
            )
        return 2
    finally:
        for client in (neo4j, postgres):
            if client is not None:
                try:
                    await client.disconnect()
                except Exception as cleanup_error:
                    print(
                        f"Graph audit cleanup warning ({type(cleanup_error).__name__})",
                        file=sys.stderr,
                    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_human(report))
    return 0 if report["status"] == "clean" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only PostgreSQL/Neo4j episode reconciliation"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    parser.add_argument(
        "--expected-sync-profile",
        help="Require this sync-profile fingerprint when node metadata is present",
    )
    parser.add_argument(
        "--expected-embedding-profile",
        help="Require this embedding-profile fingerprint when node metadata is present",
    )
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
