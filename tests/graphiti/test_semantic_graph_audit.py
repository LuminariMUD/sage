"""Tests for the read-only semantic graph audit."""

from argparse import Namespace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.graphiti.semantic_audit import (
    NORMALIZATION_POLICY,
    build_semantic_graph_audit,
    normalize_grounding_text,
)
from src.scripts import graph_semantic_audit

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _episode(stable_id: str, text: str) -> dict[str, str]:
    return {"stable_id": stable_id, "text": text}


def _document(body: str) -> dict[str, str]:
    return {"source_file": "canon/test.md", "body_md": body}


def _entity(
    uuid: str | None,
    name: str | None,
    entity_types: list[str],
    *episode_ids: str,
) -> dict[str, object]:
    return {
        "uuid": uuid,
        "name": name,
        "entity_types": entity_types,
        "episode_ids": list(episode_ids),
    }


def test_normalization_is_unicode_case_and_whitespace_stable():
    assert normalize_grounding_text("  CAFÉ\n Moon  ") == normalize_grounding_text(
        "cafe\N{COMBINING ACUTE ACCENT} moon"
    )


def test_clean_report_requires_grounded_unique_typed_entities():
    report = build_semantic_graph_audit(
        [_episode("ep-1", "The Café Moon overlooks Lumia.")],
        [_document("The cafe\N{COMBINING ACUTE ACCENT} moon overlooks Lumia.")],
        [
            _entity("entity-1", "CAFÉ MOON", ["Location"], "ep-1"),
            _entity("entity-2", "Lumia", ["Location"], "ep-1"),
        ],
        generated_at=NOW,
    )

    assert report["status"] == "clean"
    assert report["grounding_policy"]["normalization"] == NORMALIZATION_POLICY
    assert report["counts"]["graph_entities"] == 2
    assert report["counts"]["grounded_entity_episode_links"] == 2
    assert report["review_categories"] == []


def test_report_surfaces_grounding_duplicates_types_and_invalid_identity():
    report = build_semantic_graph_audit(
        [_episode("ep-1", "Crystal Dwarves live in Nagburim.")],
        [_document("Crystal Dwarves live in Nagburim.")],
        [
            _entity("entity-1", "Crystal Dwarves", ["Race"], "ep-1"),
            _entity("entity-2", "crystal dwarves", ["Person"], "ep-1"),
            _entity("entity-3", "AAN conference", ["Event"], "ep-1"),
            _entity(None, None, [], "ep-1"),
        ],
        generated_at=NOW,
    )

    counts = report["counts"]
    assert report["status"] == "review_required"
    assert counts["duplicate_name_groups"] == 1
    assert counts["entities_in_duplicate_name_groups"] == 2
    assert counts["conflicting_type_name_groups"] == 1
    assert counts["entities_absent_from_canon"] == 1
    assert counts["ungrounded_entity_episode_links"] == 1
    assert counts["ungrounded_links_for_entities_absent_from_canon"] == 1
    assert counts["ungrounded_links_for_entities_present_elsewhere_in_canon"] == 0
    assert counts["entities_without_grounded_episode_links"] == 1
    assert counts["entities_missing_uuid"] == 1
    assert counts["entities_missing_name"] == 1
    assert counts["entities_missing_type"] == 1
    assert report["samples"]["entities_absent_from_canon"][0]["name"] == "AAN conference"
    assert counts["literal_policy_evaluable_entity_episode_links"] == 3
    assert counts["literal_policy_evaluable_entities"] == 3
    assert report["rates_percent"]["literal_policy_projected_link_retention"] == 66.667
    assert report["rates_percent"]["literal_policy_projected_entity_retention"] == 66.667


def test_ungrounded_links_distinguish_global_canon_names_from_source_absence():
    report = build_semantic_graph_audit(
        [_episode("ep-1", "A local title appears here.")],
        [_document("A local title and the Global Canon Name both exist in canon.")],
        [
            _entity("entity-1", "Global Canon Name", ["Person"], "ep-1"),
            _entity("entity-2", "Prompt Example", ["Person"], "ep-1"),
        ],
        generated_at=NOW,
    )

    counts = report["counts"]
    assert counts["ungrounded_entity_episode_links"] == 2
    assert counts["ungrounded_links_for_entities_absent_from_canon"] == 1
    assert counts["ungrounded_links_for_entities_present_elsewhere_in_canon"] == 1


def test_report_finds_duplicate_uuids_missing_sources_and_episodes_without_entities():
    report = build_semantic_graph_audit(
        [
            _episode("ep-1", "Lumia"),
            _episode("ep-2", "Nagburim"),
        ],
        [_document("Lumia and Nagburim")],
        [
            _entity("same-uuid", "Lumia", ["Location"], "ep-1"),
            _entity("same-uuid", "Nagburim", ["Location"], "missing-episode"),
        ],
        generated_at=NOW,
    )

    counts = report["counts"]
    assert counts["duplicate_entity_uuid_groups"] == 1
    assert counts["missing_episode_source_links"] == 1
    assert counts["synced_episodes_without_entities"] == 1


def test_samples_are_bounded_without_changing_exact_counts():
    report = build_semantic_graph_audit(
        [_episode("ep-1", "Grounded only")],
        [_document("Grounded only")],
        [_entity(f"entity-{index}", f"Absent {index}", ["Concept"], "ep-1") for index in range(3)],
        sample_limit=1,
        generated_at=NOW,
    )

    assert report["counts"]["entities_absent_from_canon"] == 3
    assert len(report["samples"]["entities_absent_from_canon"]) == 1
    assert len(report["samples"]["ungrounded_entity_episode_links"]) == 1
    assert report["counts"]["entities_without_grounded_episode_links"] == 3


async def test_collector_uses_synced_ids_and_read_only_queries():
    episode_rows = [_episode("ep-1", "Lumia")]
    document_rows = [_document("Lumia")]
    entity_rows = [_entity("entity-1", "Lumia", ["Location"], "ep-1")]
    postgres = SimpleNamespace(
        fetch=AsyncMock(side_effect=[episode_rows, document_rows]),
    )
    neo4j = SimpleNamespace(execute_query=AsyncMock(return_value=entity_rows))

    report = await graph_semantic_audit.collect_semantic_graph_audit(postgres, neo4j)

    assert report["status"] == "clean"
    assert postgres.fetch.await_args_list[0].args == (
        graph_semantic_audit.POSTGRES_SYNCED_EPISODE_QUERY,
    )
    assert postgres.fetch.await_args_list[1].args == (
        graph_semantic_audit.POSTGRES_CANON_DOCUMENT_QUERY,
    )
    neo4j.execute_query.assert_awaited_once_with(
        graph_semantic_audit.NEO4J_SYNCED_ENTITY_QUERY,
        {"episode_ids": ["ep-1"]},
    )
    for query in (
        graph_semantic_audit.POSTGRES_SYNCED_EPISODE_QUERY,
        graph_semantic_audit.POSTGRES_CANON_DOCUMENT_QUERY,
        graph_semantic_audit.NEO4J_SYNCED_ENTITY_QUERY,
    ):
        upper_query = query.upper()
        for forbidden in ("INSERT", "UPDATE", "DELETE", "CREATE", "SET"):
            assert forbidden not in upper_query


async def test_cli_uses_read_only_clients_and_stable_exit_codes():
    args = Namespace(json=True, sample_limit=5)
    postgres = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    neo4j = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())

    with (
        patch.object(
            graph_semantic_audit,
            "PostgresDB",
            return_value=postgres,
        ) as postgres_class,
        patch.object(
            graph_semantic_audit,
            "Neo4jDB",
            return_value=neo4j,
        ) as neo4j_class,
        patch.object(
            graph_semantic_audit,
            "collect_semantic_graph_audit",
            AsyncMock(return_value={"status": "review_required"}),
        ),
        patch.object(graph_semantic_audit, "json") as json_module,
    ):
        json_module.dumps.return_value = "{}"
        assert await graph_semantic_audit.run(args) == 1

    postgres_class.assert_called_once_with(read_only=True)
    neo4j_class.assert_called_once_with(read_only=True)
    postgres.disconnect.assert_awaited_once()
    neo4j.disconnect.assert_awaited_once()


async def test_cli_returns_two_without_exposing_store_errors(capsys):
    args = Namespace(json=False, sample_limit=5)
    postgres = SimpleNamespace(
        connect=AsyncMock(side_effect=RuntimeError("secret-bearing detail")),
        disconnect=AsyncMock(),
    )
    neo4j = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())

    with (
        patch.object(graph_semantic_audit, "PostgresDB", return_value=postgres),
        patch.object(graph_semantic_audit, "Neo4jDB", return_value=neo4j),
    ):
        assert await graph_semantic_audit.run(args) == 2

    output = capsys.readouterr()
    assert "RuntimeError" in output.err
    assert "secret-bearing detail" not in output.err
