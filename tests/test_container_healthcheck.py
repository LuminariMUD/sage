"""Regression coverage for role-aware container health checks."""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from src.scripts.container_healthcheck import healthcheck_status


def _make_recipe(makefile: str, target: str) -> str:
    marker = f"{target}:"
    start = makefile.index(marker)
    lines = makefile[start:].splitlines()[1:]
    recipe: list[str] = []
    for line in lines:
        if line and not line.startswith(("\t", " ")):
            break
        recipe.append(line)
    return "\n".join(recipe)


def test_graph_worker_role_uses_a_fresh_heartbeat_and_skips_api_probe(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "worker.heartbeat"
    marker.touch()
    opener = MagicMock()

    assert (
        healthcheck_status(
            {
                "SAGE_CONTAINER_ROLE": "graph-worker",
                "SAGE_HEARTBEAT_FILE": str(marker),
                "SAGE_HEARTBEAT_MAX_AGE_SECONDS": "30",
            },
            opener,
        )
        == 0
    )
    opener.assert_not_called()


@pytest.mark.parametrize("role", ["graph-worker", "graph-watchdog", "graph-finalizer"])
def test_graph_roles_fail_closed_on_missing_heartbeat(tmp_path: Path, role: str) -> None:
    assert (
        healthcheck_status(
            {
                "SAGE_CONTAINER_ROLE": role,
                "SAGE_HEARTBEAT_FILE": str(tmp_path / "missing"),
            },
            MagicMock(),
        )
        == 1
    )


@pytest.mark.parametrize("age_seconds", [31, -301])
def test_graph_role_rejects_stale_or_implausibly_future_heartbeat(
    tmp_path: Path,
    age_seconds: int,
) -> None:
    marker = tmp_path / "worker.heartbeat"
    marker.touch()
    timestamp = time.time() - age_seconds
    os.utime(marker, (timestamp, timestamp))

    assert (
        healthcheck_status(
            {
                "SAGE_CONTAINER_ROLE": "graph-worker",
                "SAGE_HEARTBEAT_FILE": str(marker),
                "SAGE_HEARTBEAT_MAX_AGE_SECONDS": "30",
            },
            MagicMock(),
        )
        == 1
    )


def test_api_role_uses_a_bounded_loopback_probe() -> None:
    opener = MagicMock()
    response = opener.return_value.__enter__.return_value

    assert healthcheck_status({"SAGE_CONTAINER_ROLE": "api", "API_PORT": "8123"}, opener) == 0
    opener.assert_called_once_with("http://127.0.0.1:8123/api/v1/health", timeout=5)
    response.read.assert_called_once_with(1)


@pytest.mark.parametrize(
    "environment",
    [
        {"SAGE_CONTAINER_ROLE": "unexpected"},
        {"SAGE_CONTAINER_ROLE": "graph-worker"},
        {"SAGE_CONTAINER_ROLE": "graph-worker", "SAGE_HEARTBEAT_FILE": "relative"},
        {
            "SAGE_CONTAINER_ROLE": "graph-worker",
            "SAGE_HEARTBEAT_FILE": "/tmp/marker",
            "SAGE_HEARTBEAT_MAX_AGE_SECONDS": "invalid",
        },
        {"SAGE_CONTAINER_ROLE": "api", "API_PORT": "invalid"},
        {"SAGE_CONTAINER_ROLE": "api", "API_PORT": "70000"},
    ],
)
def test_invalid_healthcheck_configuration_fails_closed(environment: dict[str, str]) -> None:
    opener = MagicMock()

    assert healthcheck_status(environment, opener) == 1
    opener.assert_not_called()


def test_api_probe_failure_is_reported_as_unhealthy() -> None:
    opener = MagicMock(side_effect=OSError("connection refused"))

    assert healthcheck_status({"SAGE_CONTAINER_ROLE": "api"}, opener) == 1


@pytest.mark.parametrize(
    "target",
    ["sync-to-graphiti", "sync-to-graphiti-ollama", "sync-to-graphiti-openai"],
)
def test_graph_sync_targets_declare_the_worker_role(target: str) -> None:
    repository = Path(__file__).resolve().parents[1]
    makefile = (repository / "Makefile").read_text(encoding="utf-8")

    recipe = _make_recipe(makefile, target)

    assert "GRAPH_WORKER_ROLE_FLAG = -e SAGE_CONTAINER_ROLE=graph-worker" in makefile
    assert "$(GRAPH_WORKER_ROLE_FLAG)" in recipe
    assert "sync_episodes_to_graphiti.py" in recipe


def test_graph_sync_compose_profile_is_single_writer_managed_and_heartbeat_checked() -> None:
    repository = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((repository / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    worker = services["graph-sync-worker"]

    assert worker["profiles"] == ["graph-sync"]
    assert worker["deploy"]["replicas"] == 1
    assert worker["restart"] == "on-failure:10"
    assert "--managed" in worker["command"]
    assert "--idle-poll-seconds" in worker["command"]
    assert worker["environment"]["SAGE_CONTAINER_ROLE"] == "graph-worker"
    for service_name, role in (
        ("graph-sync-watchdog", "graph-watchdog"),
        ("graph-sync-finalizer", "graph-finalizer"),
    ):
        service = services[service_name]
        assert service["profiles"] == ["graph-sync"]
        assert service["environment"]["SAGE_CONTAINER_ROLE"] == role
        assert service["healthcheck"]["test"] == [
            "CMD",
            "python",
            "src/scripts/container_healthcheck.py",
        ]
