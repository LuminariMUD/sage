"""Regression coverage for provider-specific Graphiti capacity defaults."""

from pathlib import Path

import yaml


def _example_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        values[name] = value.split(" #", 1)[0].strip()
    return values


def _compose_environment(path: Path) -> dict[str, str]:
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))
    return compose["services"]["api"]["environment"]


def _assert_provider_capacity_contract(environment: dict[str, str]) -> None:
    assert environment["OLLAMA_GRAPHITI_MAX_PROVIDER_CALLS"] == (
        "${OLLAMA_GRAPHITI_MAX_PROVIDER_CALLS:-100}"
    )
    assert environment["OPENROUTER_GRAPHITI_MAX_PROVIDER_CALLS"] == (
        "${OPENROUTER_GRAPHITI_MAX_PROVIDER_CALLS:-16}"
    )
    assert environment["OPENAI_GRAPHITI_MAX_PROVIDER_CALLS"] == (
        "${OPENAI_GRAPHITI_MAX_PROVIDER_CALLS:-32}"
    )
    assert environment["GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS"] == (
        "${GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS:-}"
    )
    assert environment["GRAPH_SYNC_MAX_PROVIDER_CALLS"] == ("${GRAPH_SYNC_MAX_PROVIDER_CALLS:-}")


def test_development_compose_uses_provider_specific_capacity_defaults() -> None:
    repository = Path(__file__).resolve().parents[1]

    _assert_provider_capacity_contract(_compose_environment(repository / "docker-compose.yml"))


def test_production_compose_uses_provider_specific_capacity_defaults() -> None:
    repository = Path(__file__).resolve().parents[1]

    _assert_provider_capacity_contract(_compose_environment(repository / "docker-compose.prod.yml"))


def test_example_environment_keeps_legacy_overrides_empty() -> None:
    repository = Path(__file__).resolve().parents[1]
    environment = _example_environment(repository / ".env.example")

    assert environment["OLLAMA_GRAPHITI_MAX_PROVIDER_CALLS"] == "100"
    assert environment["OPENROUTER_GRAPHITI_MAX_PROVIDER_CALLS"] == "16"
    assert environment["OPENAI_GRAPHITI_MAX_PROVIDER_CALLS"] == "32"
    assert environment["GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS"] == ""
    assert environment["GRAPH_SYNC_MAX_PROVIDER_CALLS"] == ""
