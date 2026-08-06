"""Tests for the read-only graph reconciliation command."""

from argparse import Namespace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.graphiti.audit import build_graph_audit, source_content_fingerprint
from src.scripts import graph_audit

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def _episode(stable_id: str, *, synced: bool = True, text: str = "Lore") -> dict:
    return {"stable_id": stable_id, "text": text, "graphiti_synced": synced}


def _node(stable_id: str | None, **overrides) -> dict:
    values = {
        "stable_id": stable_id,
        "source_description": f"episode_{stable_id}" if stable_id else None,
        "source_fingerprint": None,
        "sync_profile_fingerprint": None,
        "embedding_profile_fingerprint": None,
    }
    values.update(overrides)
    return values


def test_clean_legacy_projection_is_reported_without_requiring_new_metadata():
    report = build_graph_audit(
        [_episode("ep-1"), _episode("ep-2", synced=False)],
        [_node("ep-1")],
        generated_at=NOW,
    )

    assert report["status"] == "clean"
    assert report["state_source"] == "legacy_projection"
    assert report["counts"]["lifecycle"] == {
        "pending": 1,
        "leased": 0,
        "retry_wait": 0,
        "quarantined": 0,
        "synced": 1,
    }
    assert report["counts"]["drift_findings"] == 0


def test_audit_reports_every_cross_store_drift_class():
    episodes = [
        _episode("missing"),
        _episode("duplicate"),
        _episode("pending", synced=False),
        _episode("wrong-description"),
        _episode("wrong-fingerprint", text="Current lore"),
        _episode("wrong-profiles"),
    ]
    nodes = [
        _node("duplicate"),
        _node("duplicate"),
        _node("pending"),
        _node("unexpected"),
        _node(None),
        _node("wrong-description", source_description="not_the_episode"),
        _node("wrong-fingerprint", source_fingerprint="sha256:v1:stale"),
        _node(
            "wrong-profiles",
            sync_profile_fingerprint="sync-old",
            embedding_profile_fingerprint="embedding-old",
        ),
    ]

    report = build_graph_audit(
        episodes,
        nodes,
        expected_sync_profile="sync-current",
        expected_embedding_profile="embedding-current",
        generated_at=NOW,
    )

    assert report["status"] == "drift"
    assert report["drift"]["missing_neo4j_ids"] == ["missing"]
    assert report["drift"]["unexpected_neo4j_ids"] == ["unexpected"]
    assert report["drift"]["duplicate_stable_ids"] == [{"stable_id": "duplicate", "count": 2}]
    assert report["drift"]["null_stable_id_count"] == 1
    assert report["drift"]["neo4j_present_for_non_synced_jobs"] == ["pending"]
    assert len(report["drift"]["source_description_mismatches"]) == 1
    assert len(report["drift"]["source_fingerprint_mismatches"]) == 1
    assert len(report["drift"]["sync_profile_mismatches"]) == 1
    assert len(report["drift"]["embedding_profile_mismatches"]) == 1


def test_durable_jobs_replace_boolean_as_authoritative_state():
    fingerprint = source_content_fingerprint("Lore")
    jobs = [
        {
            "stable_id": "ep-1",
            "state": "synced",
            "desired_source_fingerprint": fingerprint,
            "verified_at": NOW,
        },
        {
            "stable_id": "ep-2",
            "state": "pending",
            "desired_source_fingerprint": fingerprint,
            "verified_at": None,
        },
    ]

    report = build_graph_audit(
        [_episode("ep-1"), _episode("ep-2", synced=False)],
        [_node("ep-1")],
        jobs,
        generated_at=NOW,
    )

    assert report["status"] == "clean"
    assert report["state_source"] == "graph_sync_jobs"
    assert report["counts"]["postgres_synced"] == 1


def test_durable_job_projection_and_fingerprint_errors_are_drift():
    report = build_graph_audit(
        [_episode("ep-1", synced=True, text="New")],
        [_node("ep-1")],
        [
            {
                "stable_id": "ep-1",
                "state": "pending",
                "desired_source_fingerprint": source_content_fingerprint("Old"),
                "verified_at": None,
            }
        ],
        generated_at=NOW,
    )

    reasons = {finding["reason"] for finding in report["drift"]["incorrectly_synchronized_jobs"]}
    assert report["status"] == "drift"
    assert reasons == {"non_synced_job_legacy_flag_true"}
    assert len(report["drift"]["stale_job_source_fingerprints"]) == 1


async def test_collect_graph_audit_uses_only_read_queries():
    postgres = SimpleNamespace(
        fetch=AsyncMock(side_effect=[[_episode("ep-1")]]),
        fetchval=AsyncMock(return_value=False),
    )
    neo4j = SimpleNamespace(execute_query=AsyncMock(return_value=[_node("ep-1")]))

    report = await graph_audit.collect_graph_audit(postgres, neo4j)

    assert report["status"] == "clean"
    postgres.fetch.assert_awaited_once_with(graph_audit.POSTGRES_EPISODE_QUERY)
    neo4j.execute_query.assert_awaited_once_with(graph_audit.NEO4J_EPISODE_QUERY)
    assert "SELECT" in graph_audit.POSTGRES_EPISODE_QUERY.upper()
    assert "MATCH" in graph_audit.NEO4J_EPISODE_QUERY.upper()
    for forbidden in ("INSERT", "UPDATE", "DELETE", "CREATE", "SET"):
        assert forbidden not in graph_audit.POSTGRES_EPISODE_QUERY.upper()
        assert forbidden not in graph_audit.NEO4J_EPISODE_QUERY.upper()


async def test_cli_uses_read_only_clients_and_stable_exit_codes():
    args = Namespace(
        json=True,
        expected_sync_profile=None,
        expected_embedding_profile=None,
    )
    postgres = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    neo4j = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())

    with (
        patch.object(graph_audit, "PostgresDB", return_value=postgres) as postgres_class,
        patch.object(graph_audit, "Neo4jDB", return_value=neo4j) as neo4j_class,
        patch.object(
            graph_audit,
            "collect_graph_audit",
            AsyncMock(return_value={"status": "clean"}),
        ),
        patch.object(graph_audit, "json") as json_module,
    ):
        json_module.dumps.return_value = "{}"
        assert await graph_audit.run(args) == 0

    postgres_class.assert_called_once_with(read_only=True)
    neo4j_class.assert_called_once_with(read_only=True)
    postgres.disconnect.assert_awaited_once()
    neo4j.disconnect.assert_awaited_once()


async def test_cli_returns_one_for_discovered_drift():
    args = Namespace(
        json=True,
        expected_sync_profile=None,
        expected_embedding_profile=None,
    )
    postgres = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    neo4j = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())

    with (
        patch.object(graph_audit, "PostgresDB", return_value=postgres),
        patch.object(graph_audit, "Neo4jDB", return_value=neo4j),
        patch.object(
            graph_audit,
            "collect_graph_audit",
            AsyncMock(return_value={"status": "drift"}),
        ),
        patch.object(graph_audit, "json") as json_module,
    ):
        json_module.dumps.return_value = "{}"
        assert await graph_audit.run(args) == 1


async def test_cli_returns_two_when_a_store_cannot_be_read(capsys):
    args = Namespace(
        json=False,
        expected_sync_profile=None,
        expected_embedding_profile=None,
    )
    postgres = SimpleNamespace(
        connect=AsyncMock(side_effect=RuntimeError("secret-bearing driver detail")),
        disconnect=AsyncMock(),
    )
    neo4j = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())

    with (
        patch.object(graph_audit, "PostgresDB", return_value=postgres),
        patch.object(graph_audit, "Neo4jDB", return_value=neo4j),
    ):
        assert await graph_audit.run(args) == 2

    captured = capsys.readouterr()
    assert "RuntimeError" in captured.err
    assert "secret-bearing" not in captured.err


async def test_cli_returns_two_when_client_configuration_is_invalid(capsys):
    args = Namespace(
        json=False,
        expected_sync_profile=None,
        expected_embedding_profile=None,
    )

    with patch.object(
        graph_audit,
        "PostgresDB",
        side_effect=ValueError("missing credential details must stay private"),
    ):
        assert await graph_audit.run(args) == 2

    captured = capsys.readouterr()
    assert "ValueError" in captured.err
    assert "credential details" not in captured.err
