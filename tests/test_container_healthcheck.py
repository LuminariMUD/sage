"""Regression coverage for role-aware container health checks."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

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


def test_graph_worker_role_skips_the_api_probe() -> None:
    opener = MagicMock()

    assert healthcheck_status({"SAGE_CONTAINER_ROLE": "graph-worker"}, opener) == 0
    opener.assert_not_called()


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
