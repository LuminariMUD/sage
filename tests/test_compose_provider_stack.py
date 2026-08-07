"""Offline tests for capability-aware development Compose selection."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from src.scripts.compose_provider_stack import (
    BASE_COMPOSE_FILE,
    NO_OLLAMA_COMPOSE_FILE,
    ComposeProviderStackError,
    _parse_ollama_init_environment,
    build_compose_command,
    render_plan,
    select_compose_stack,
)


def _provider_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "LLM_PROVIDER": "ollama",
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "USE_LOCAL_EMBEDDINGS": "true",
        "GRAPHITI_PROVIDER": "",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "",
        "OLLAMA_CHAT_MODEL": "qwen2.5:7b",
        "OLLAMA_CREATIVE_MODEL": "qwen2.5:7b",
        "OLLAMA_REASONING_MODEL": "qwen2.5:3b",
        "OLLAMA_EXTRACTION_MODEL": "qwen2.5:3b",
        "OLLAMA_TOOLS_MODEL": "qwen2.5:7b",
        "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
    }
    environment.update(overrides)
    return environment


def _compose_services(*compose_files: Path, **overrides: str) -> set[str]:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose rendering is a host-only contract check")
    command = ["docker", "compose"]
    for compose_file in compose_files:
        command.extend(("-f", str(compose_file)))
    command.extend(("config", "--services"))
    environment = {
        **os.environ,
        "POSTGRES_PASSWORD": "offline-compose-password",
        "NEO4J_PASSWORD": "offline-compose-password",
        "SAGE_API_KEY": "offline-compose-api-key",
        "OPENROUTER_API_KEY": "offline-compose-openrouter-key",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "",
        **overrides,
    }
    result = subprocess.run(
        command,
        cwd=BASE_COMPOSE_FILE.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return set(result.stdout.splitlines())


def test_all_ollama_selection_keeps_backward_compatible_base_stack():
    selection = select_compose_stack(_provider_environment())

    assert selection.mode == "ollama-required"
    assert selection.ollama_required is True
    assert selection.ollama_models == (
        "text:qwen2.5:7b",
        "text:qwen2.5:3b",
        "embedding:nomic-embed-text",
    )
    assert selection.compose_files == (BASE_COMPOSE_FILE,)


def test_all_openrouter_selection_adds_no_ollama_override():
    selection = select_compose_stack(
        _provider_environment(
            LLM_PROVIDER="openrouter",
            TEXT_PROVIDER="openrouter",
            EMBEDDING_PROVIDER="openrouter",
            GRAPHITI_TEXT_PROVIDER="openrouter",
            GRAPHITI_EMBEDDING_PROVIDER="openrouter",
        )
    )

    assert selection.mode == "ollama-not-required"
    assert selection.ollama_required is False
    assert selection.ollama_models == ()
    assert selection.compose_files == (BASE_COMPOSE_FILE, NO_OLLAMA_COMPOSE_FILE)
    assert render_plan(selection) == (
        "mode: ollama-not-required\nollama_required: false\nollama_model_count: 0"
    )


def test_mixed_selection_keeps_ollama_for_one_local_capability():
    selection = select_compose_stack(
        _provider_environment(
            TEXT_PROVIDER="openrouter",
            EMBEDDING_PROVIDER="openrouter",
            GRAPHITI_TEXT_PROVIDER="openrouter",
            GRAPHITI_EMBEDDING_PROVIDER="ollama",
        )
    )

    assert selection.mode == "ollama-required"
    assert selection.ollama_models == ("embedding:nomic-embed-text",)


def test_invalid_provider_configuration_fails_before_compose_execution():
    with pytest.raises(
        ComposeProviderStackError,
        match="Selected provider capability configuration is invalid",
    ):
        select_compose_stack(_provider_environment(TEXT_PROVIDER="invalid-provider"))


def test_compose_environment_parser_rejects_sensitive_init_fields():
    payload = (
        '{"services":{"ollama-init":{"environment":'
        '{"TEXT_PROVIDER":"ollama","OPENROUTER_API_KEY":"secret"}}}}'
    )

    with pytest.raises(
        ComposeProviderStackError,
        match="contains a sensitive field",
    ):
        _parse_ollama_init_environment(payload)


def test_compose_command_contains_only_selected_files_and_user_arguments():
    selection = select_compose_stack(
        _provider_environment(
            LLM_PROVIDER="openrouter",
            TEXT_PROVIDER="openrouter",
            EMBEDDING_PROVIDER="openrouter",
            GRAPHITI_TEXT_PROVIDER="openrouter",
            GRAPHITI_EMBEDDING_PROVIDER="openrouter",
        )
    )

    command = build_compose_command(selection, ("up", "-d", "--build"))

    assert command == [
        "docker",
        "compose",
        "-f",
        str(BASE_COMPOSE_FILE),
        "-f",
        str(NO_OLLAMA_COMPOSE_FILE),
        "up",
        "-d",
        "--build",
    ]
    assert not any("key" in argument.lower() for argument in command)


def test_no_ollama_override_omits_local_services_from_cloud_only_render():
    services = _compose_services(
        BASE_COMPOSE_FILE,
        NO_OLLAMA_COMPOSE_FILE,
        LLM_PROVIDER="openrouter",
        TEXT_PROVIDER="openrouter",
        EMBEDDING_PROVIDER="openrouter",
        GRAPHITI_TEXT_PROVIDER="openrouter",
        GRAPHITI_EMBEDDING_PROVIDER="openrouter",
    )

    assert {"postgres", "neo4j", "api", "ui"} <= services
    assert "ollama" not in services
    assert "ollama-init" not in services


def test_base_compose_still_contains_ollama_for_the_default_local_profile():
    services = _compose_services(
        BASE_COMPOSE_FILE,
        LLM_PROVIDER="ollama",
        TEXT_PROVIDER="ollama",
        EMBEDDING_PROVIDER="ollama",
        GRAPHITI_TEXT_PROVIDER="ollama",
        GRAPHITI_EMBEDDING_PROVIDER="ollama",
    )

    assert {"ollama", "ollama-init", "postgres", "neo4j", "api", "ui"} <= services


def test_override_and_makefile_keep_selection_host_side_and_secret_free():
    project_dir = BASE_COMPOSE_FILE.parent
    override = yaml.safe_load(NO_OLLAMA_COMPOSE_FILE.read_text(encoding="utf-8"))
    makefile = (project_dir / "Makefile").read_text(encoding="utf-8")

    assert override["services"]["ollama"]["profiles"] == ["local-ollama"]
    assert override["services"]["ollama-init"]["profiles"] == ["local-ollama"]
    assert override["services"]["api"]["depends_on"]["ollama"]["required"] is False
    assert override["services"]["api"]["depends_on"]["ollama-init"]["required"] is False
    assert "src/scripts/compose_provider_stack.py" in makefile
    assert "$(PROVIDER_COMPOSE) up -d --build --remove-orphans" in makefile
    assert "docker compose down" in makefile
    assert "OPENROUTER_API_KEY" not in NO_OLLAMA_COMPOSE_FILE.read_text(encoding="utf-8")
