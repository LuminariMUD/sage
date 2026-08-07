"""Offline contract tests for capability-derived Ollama model lifecycle."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _script() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "ollama_model_profile.sh"


def _environment(**overrides: str) -> dict[str, str]:
    environment = {
        "PATH": os.environ["PATH"],
        "LLM_PROVIDER": "ollama",
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "GRAPHITI_PROVIDER": "",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "",
    }
    environment.update(overrides)
    return environment


def _run(action: str = "list", **overrides: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(_script()), action],
        env=_environment(**overrides),
        capture_output=True,
        text=True,
        check=False,
    )


def test_all_ollama_profile_lists_each_required_model_once():
    result = _run()

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "text:qwen2.5:7b",
        "text:qwen2.5:3b",
        "embedding:nomic-embed-text",
    ]


def test_all_openrouter_profile_skips_ollama_models_and_cli_requirement():
    result = _run(
        "pull",
        LLM_PROVIDER="openrouter",
        TEXT_PROVIDER="openrouter",
        EMBEDDING_PROVIDER="openrouter",
        GRAPHITI_TEXT_PROVIDER="openrouter",
        GRAPHITI_EMBEDDING_PROVIDER="openrouter",
    )

    assert result.returncode == 0, result.stderr
    assert "No Ollama capability selected" in result.stdout


def test_mixed_profile_includes_only_selected_local_capability_models():
    result = _run(
        TEXT_PROVIDER="openrouter",
        EMBEDDING_PROVIDER="ollama",
        GRAPHITI_TEXT_PROVIDER="ollama",
        GRAPHITI_EMBEDDING_PROVIDER="openrouter",
        GRAPHITI_TEXT_MODEL="qwen2.5:graph-custom",
        GRAPHITI_EXTRACTION_FALLBACK_PROVIDER="ollama",
        GRAPHITI_EXTRACTION_FALLBACK_MODEL="qwen2.5:fallback-custom",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "text:qwen2.5:graph-custom",
        "text:qwen2.5:fallback-custom",
        "embedding:nomic-embed-text",
    ]


def test_task_specific_models_are_deduplicated_without_losing_overrides():
    result = _run(
        GRAPHITI_TEXT_PROVIDER="openrouter",
        GRAPHITI_EMBEDDING_PROVIDER="openrouter",
        OLLAMA_CHAT_MODEL="local/chat",
        OLLAMA_CREATIVE_MODEL="local/creative",
        OLLAMA_REASONING_MODEL="local/reasoning",
        OLLAMA_EXTRACTION_MODEL="local/reasoning",
        OLLAMA_TOOLS_MODEL="local/chat",
        OLLAMA_EMBEDDING_MODEL="local/embed",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "text:local/chat",
        "text:local/creative",
        "text:local/reasoning",
        "embedding:local/embed",
    ]


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("TEXT_PROVIDER", "unsupported"),
        ("OLLAMA_CHAT_MODEL", "--unsafe-option"),
        ("OLLAMA_CHAT_MODEL", "model with spaces"),
        ("GRAPHITI_EXTRACTION_FALLBACK_PROVIDER", "ollama"),
    ),
)
def test_invalid_provider_or_model_configuration_fails_closed(name: str, value: str):
    result = _run(**{name: value})

    assert result.returncode == 2
    assert result.stdout == ""


def test_pull_action_invokes_each_unique_model_once(tmp_path: Path):
    call_log = tmp_path / "ollama-calls"
    fake_ollama = tmp_path / "ollama"
    fake_ollama.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$OLLAMA_TEST_CALL_LOG"\n',
        encoding="utf-8",
    )
    fake_ollama.chmod(0o755)

    result = _run(
        "pull",
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        OLLAMA_TEST_CALL_LOG=str(call_log),
    )

    assert result.returncode == 0, result.stderr
    assert call_log.read_text(encoding="utf-8").splitlines() == [
        "pull qwen2.5:7b",
        "pull qwen2.5:3b",
        "pull nomic-embed-text",
    ]


def test_compose_and_lifecycle_scripts_use_the_shared_profile_resolver():
    project_dir = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project_dir / "docker-compose.yml").read_text(encoding="utf-8"))
    init = compose["services"]["ollama-init"]
    api_environment = compose["services"]["api"]["environment"]
    setup = (project_dir / "scripts" / "setup_ollama_models.sh").read_text(encoding="utf-8")
    warmup = (project_dir / "scripts" / "warmup_models.sh").read_text(encoding="utf-8")

    assert init["entrypoint"] == [
        "/bin/sh",
        "/usr/local/bin/ollama_model_profile.sh",
        "pull",
    ]
    assert not any("KEY" in name or "PASSWORD" in name for name in init["environment"])
    assert api_environment["TEXT_PROVIDER"] == "${TEXT_PROVIDER:-}"
    assert api_environment["EMBEDDING_PROVIDER"] == "${EMBEDDING_PROVIDER:-}"
    assert api_environment["GRAPHITI_PROVIDER"] == "${GRAPHITI_PROVIDER:-}"
    assert "ollama_model_profile.sh list" in setup
    assert "ollama_model_profile.sh list" in warmup
    assert "/api/embed" in warmup
