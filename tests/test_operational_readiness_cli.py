"""Tests for the read-only operational readiness command."""

import json
from unittest.mock import AsyncMock, Mock

from src.scripts import operational_readiness


async def test_run_uses_read_only_clients_and_stable_ready_exit(capsys):
    args = operational_readiness.build_parser().parse_args(["--json"])
    postgres = AsyncMock()
    neo4j = AsyncMock()
    postgres_factory = Mock(return_value=postgres)
    neo4j_factory = Mock(return_value=neo4j)
    collector = AsyncMock(
        return_value={
            "schema_version": 1,
            "status": "ready",
            "ready": True,
        }
    )

    exit_code = await operational_readiness.run(
        args,
        postgres_factory=postgres_factory,
        neo4j_factory=neo4j_factory,
        settings_resolver=Mock(return_value=object()),
        sync_profile_resolver=Mock(return_value=object()),
        report_collector=collector,
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    postgres_factory.assert_called_once_with(read_only=True)
    neo4j_factory.assert_called_once_with(read_only=True)
    postgres.connect.assert_awaited_once()
    neo4j.connect.assert_awaited_once()
    postgres.disconnect.assert_awaited_once()
    neo4j.disconnect.assert_awaited_once()
    collector.assert_awaited_once()


async def test_run_returns_one_when_alerts_need_attention(capsys):
    args = operational_readiness.build_parser().parse_args(["--json"])
    collector = AsyncMock(
        return_value={
            "schema_version": 1,
            "status": "blocked",
            "ready": False,
        }
    )

    exit_code = await operational_readiness.run(
        args,
        postgres_factory=Mock(return_value=AsyncMock()),
        neo4j_factory=Mock(return_value=AsyncMock()),
        settings_resolver=Mock(return_value=object()),
        sync_profile_resolver=Mock(return_value=object()),
        report_collector=collector,
    )

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_load_baseline_rejects_unrelated_json(tmp_path):
    path = tmp_path / "not-a-readiness-report.json"
    path.write_text('{"schema_version": 1}', encoding="utf-8")

    try:
        operational_readiness.load_baseline(path)
    except ValueError as error:
        assert "incomplete" in str(error)
    else:
        raise AssertionError("Unrelated JSON was accepted as a readiness baseline")
