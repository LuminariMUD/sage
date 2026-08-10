#!/usr/bin/env python3
"""Read-only semantic grounding and entity-consistency audit."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any
from uuid import UUID

sys.path.insert(0, "/app")

from src.db.neo4j_db import Neo4jDB
from src.db.postgres import PostgresDB
from src.graphiti.semantic_audit import build_semantic_graph_audit
from src.graphiti.semantic_audit_store import SemanticAuditRepository
from src.graphiti.sync_state import GraphSyncRepository

PERSIST_CONFIRMATION = "PERSIST_SEMANTIC_AUDIT"

POSTGRES_SYNCED_EPISODE_QUERY = """
    SELECT episode.id::text AS stable_id, episode.text
    FROM episodes AS episode
    JOIN graph_sync_jobs AS job ON job.episode_id = episode.id
    WHERE job.state = 'synced'
      AND job.desired_operation = 'sync'
      AND episode.retired_at IS NULL
      AND episode.graph_extraction_eligible IS TRUE
    ORDER BY episode.id
"""

POSTGRES_CANON_DOCUMENT_QUERY = """
    SELECT source_file, body_md
    FROM lore_documents
    WHERE canonical IS TRUE
    ORDER BY source_file
"""

NEO4J_SYNCED_ENTITY_QUERY = """
    MATCH (episode:Episodic)-[:MENTIONS]->(entity:Entity)
    WHERE episode.stable_id IN $episode_ids
    WITH entity, collect(DISTINCT episode.stable_id) AS mentioned_episode_ids
    RETURN entity.uuid AS uuid,
           entity.name AS name,
           [label IN labels(entity) WHERE NOT label IN ['Entity', 'Entity_']] AS entity_types,
           mentioned_episode_ids AS episode_ids
    ORDER BY name, uuid
"""


async def collect_semantic_graph_audit(
    postgres: PostgresDB,
    neo4j: Neo4jDB,
    *,
    sample_limit: int = 20,
    include_evidence: bool = False,
) -> dict[str, Any]:
    """Collect consistent read-only inputs and build the semantic report."""
    episode_rows = await postgres.fetch(POSTGRES_SYNCED_EPISODE_QUERY)
    document_rows = await postgres.fetch(POSTGRES_CANON_DOCUMENT_QUERY)
    episode_ids = [str(row["stable_id"]) for row in episode_rows]
    entity_rows = await neo4j.execute_query(
        NEO4J_SYNCED_ENTITY_QUERY,
        {"episode_ids": episode_ids},
    )
    return build_semantic_graph_audit(
        episode_rows,
        document_rows,
        entity_rows,
        sample_limit=sample_limit,
        include_evidence=include_evidence,
    )


def render_human(report: dict[str, Any]) -> str:
    """Render a compact review-oriented report without source text."""
    counts = report["counts"]
    lines = [
        "Semantic graph audit: " + report["status"].upper(),
        f"Scope: {report['scope']}",
        (
            "Corpus: "
            f"canonical_documents={counts['canonical_documents']}, "
            f"synced_episodes={counts['synced_episodes']}"
        ),
        (
            "Entities: "
            f"total={counts['graph_entities']}, "
            f"missing_uuid={counts['entities_missing_uuid']}, "
            f"missing_name={counts['entities_missing_name']}, "
            f"missing_type={counts['entities_missing_type']}"
        ),
        (
            "Grounding: "
            f"links={counts['entity_episode_links']}, "
            f"grounded={counts['grounded_entity_episode_links']}, "
            f"ungrounded={counts['ungrounded_entity_episode_links']}, "
            "ungrounded_entity_absent="
            f"{counts['ungrounded_links_for_entities_absent_from_canon']}, "
            "ungrounded_entity_present_elsewhere="
            f"{counts['ungrounded_links_for_entities_present_elsewhere_in_canon']}, "
            f"absent_from_canon={counts['entities_absent_from_canon']}, "
            f"entities_without_grounded_links="
            f"{counts['entities_without_grounded_episode_links']}"
        ),
        (
            "Literal-policy projection: "
            "evaluable_links="
            f"{counts['literal_policy_evaluable_entity_episode_links']}, "
            f"evaluable_entities={counts['literal_policy_evaluable_entities']}, "
            "link_retention="
            f"{report['rates_percent']['literal_policy_projected_link_retention']}%, "
            "entity_retention="
            f"{report['rates_percent']['literal_policy_projected_entity_retention']}%"
        ),
        (
            "Identity signals: "
            f"duplicate_uuid_groups={counts['duplicate_entity_uuid_groups']}, "
            f"duplicate_name_groups={counts['duplicate_name_groups']}, "
            f"entities_in_duplicate_name_groups="
            f"{counts['entities_in_duplicate_name_groups']}, "
            f"conflicting_type_groups={counts['conflicting_type_name_groups']}"
        ),
        "Review categories: " + (", ".join(report["review_categories"]) or "none"),
    ]
    for category, samples in report["samples"].items():
        if not samples:
            continue
        lines.append(f"- {category} sample ({len(samples)}):")
        lines.extend("  - " + json.dumps(sample, sort_keys=True) for sample in samples)
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> int:
    """Execute the audit with stable clean/review/incomplete exit codes."""
    persist = bool(getattr(args, "persist", False))
    confirmation = getattr(args, "confirm", None)
    run_id = getattr(args, "run_id", None)
    if persist and confirmation != PERSIST_CONFIRMATION:
        print(
            f"Semantic graph audit rejected: --confirm {PERSIST_CONFIRMATION} is required",
            file=sys.stderr,
        )
        return 2
    postgres = None
    neo4j = None
    try:
        postgres = PostgresDB(read_only=not persist)
        neo4j = Neo4jDB(read_only=True)
        await postgres.connect()
        await neo4j.connect()
        report = await collect_semantic_graph_audit(
            postgres,
            neo4j,
            sample_limit=args.sample_limit,
            include_evidence=persist,
        )
        report["entity_stage_quality"] = await GraphSyncRepository(
            postgres
        ).entity_stage_quality_report(run_id)
        if persist:
            persistence = await SemanticAuditRepository(postgres).persist(
                report,
                run_id=run_id,
            )
            report["persistence"] = persistence
    except Exception as error:
        incomplete = {
            "schema_version": 1,
            "status": "incomplete",
            "error_type": type(error).__name__,
            "message": "Semantic graph audit could not complete",
        }
        if args.json:
            print(json.dumps(incomplete, indent=2, sort_keys=True))
        else:
            print(
                f"Semantic graph audit: INCOMPLETE ({incomplete['error_type']})",
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
                        f"Semantic graph audit cleanup warning ({type(cleanup_error).__name__})",
                        file=sys.stderr,
                    )

    visible_report = dict(report)
    visible_report.pop("evidence", None)
    if args.json:
        print(json.dumps(visible_report, indent=2, sort_keys=True, default=str))
    else:
        output = render_human(visible_report)
        if persist:
            persistence = visible_report["persistence"]
            output += (
                "\nPersisted snapshot: "
                f"{persistence['snapshot_id']} "
                f"(created={str(persistence['created']).lower()}, "
                f"transitions={persistence['transition_count']})"
            )
        print(output)
    return 0 if report["status"] == "clean" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review literal entity grounding, duplicate names, and type consistency"
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="Maximum sample records per finding category (default: 20)",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist content-free snapshot and entity transitions",
    )
    parser.add_argument("--confirm", help=f"Required with --persist: {PERSIST_CONFIRMATION}")
    parser.add_argument("--run-id", type=UUID, help="Optional durable graph run association")
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
