"""Regression coverage for production secret-file deployment."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from dotenv import dotenv_values

SECRET_ENV_NAMES = (
    "POSTGRES_PASSWORD",
    "NEO4J_PASSWORD",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "LANGSMITH_API_KEY",
    "SAGE_API_KEY",
    "SAGE_MCP_KEY",
    "SAGE_MCP_BACKEND_KEY",
)

DEPLOY_INPUT_NAMES = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "LANGSMITH_API_KEY",
    "SAGE_API_KEY",
    "SAGE_MCP_KEY",
    "SAGE_MCP_BACKEND_KEY",
    "GHCR_ACTOR",
    "GHCR_TOKEN",
    "SAGE_IMAGE",
    "TEXT_PROVIDER",
    "EMBEDDING_PROVIDER",
    "GRAPHITI_TEXT_PROVIDER",
    "GRAPHITI_EMBEDDING_PROVIDER",
    "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER",
    "GRAPHITI_EXTRACTION_FALLBACK_MODEL",
    "OPENROUTER_CHAT_MODEL",
    "OPENROUTER_GRAPHITI_MODEL",
    "OPENROUTER_EMBEDDING_MODEL",
    "OLLAMA_BASE_URL",
)


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _deployment_values(unique: str, **overrides: str) -> dict[str, str]:
    values = {
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": f"pg '$ {unique} \\\\ value",
        "POSTGRES_DB": "app_db",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": f"neo '$ {unique} \\\\ value",
        "OPENAI_API_KEY": f"openai-{unique}",
        "OPENROUTER_API_KEY": "",
        "LANGSMITH_API_KEY": "",
        "SAGE_API_KEY": f"api-{unique}",
        "SAGE_MCP_KEY": f"mcp-{unique}",
        "SAGE_MCP_BACKEND_KEY": f"backend-{unique}",
        "GHCR_ACTOR": "ci-actor",
        "GHCR_TOKEN": f"registry-{unique}",
        "SAGE_IMAGE": "ghcr.io/luminarimud/sage@sha256:" + ("a" * 64),
        "TEXT_PROVIDER": "openai",
        "EMBEDDING_PROVIDER": "openai",
        "GRAPHITI_TEXT_PROVIDER": "openai",
        "GRAPHITI_EMBEDDING_PROVIDER": "openai",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "",
        "GRAPHITI_EXTRACTION_FALLBACK_MODEL": "",
        "OPENROUTER_CHAT_MODEL": "",
        "OPENROUTER_GRAPHITI_MODEL": "",
        "OPENROUTER_EMBEDDING_MODEL": "",
        "OLLAMA_BASE_URL": "",
    }
    values.update(overrides)
    return values


def _deployment_payload(values: dict[str, str]) -> bytes:
    return b"\0".join(values[name].encode() for name in DEPLOY_INPUT_NAMES) + b"\0"


def _prepare_deployment_stubs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    transfer_dir = tmp_path / "transfer"
    deploy_dir = tmp_path / "deploy"
    bin_dir = tmp_path / "bin"
    command_log = tmp_path / "commands.log"
    transfer_dir.mkdir()
    bin_dir.mkdir()
    for compose_name in (
        "docker-compose.yml",
        "docker-compose.openai.yml",
        "docker-compose.openrouter.yml",
    ):
        (transfer_dir / compose_name).write_text("services: {}\n", encoding="utf-8")
    (transfer_dir / "postgresql_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")

    _write_executable(
        bin_dir / "docker-stub",
        """#!/usr/bin/env bash
set -euo pipefail
for name in \
    POSTGRES_PASSWORD_ENV \
    NEO4J_PASSWORD_ENV \
    OPENAI_API_KEY_ENV \
    OPENROUTER_API_KEY_ENV \
    LANGSMITH_API_KEY_ENV \
    SAGE_API_KEY_ENV \
    SAGE_MCP_KEY_ENV \
    SAGE_MCP_BACKEND_KEY_ENV \
    GHCR_TOKEN_ENV
do
    if [[ -n "${!name+x}" ]]; then
        echo "deployment input leaked to child environment: $name" >&2
        exit 97
    fi
done
printf '%s\n' "$*" >> "$SAGE_TEST_COMMAND_LOG"
if [[ "${1:-}" == "login" ]]; then
    read -r _ || true
fi
""",
    )
    _write_executable(bin_dir / "curl-stub", "#!/usr/bin/env bash\nexit 0\n")
    return transfer_dir, deploy_dir, bin_dir, command_log


def _run_remote_deploy(
    project_dir: Path,
    values: dict[str, str],
    transfer_dir: Path,
    deploy_dir: Path,
    bin_dir: Path,
    command_log: Path,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    for name in (*SECRET_ENV_NAMES, "OPENROUTER_KEY"):
        env.pop(name, None)
        env.pop(f"{name}_FILE", None)
    env.update(
        {
            "SAGE_TRANSFER_DIR": str(transfer_dir),
            "SAGE_DEPLOY_DIR": str(deploy_dir),
            "SAGE_DOCKER_BIN": str(bin_dir / "docker-stub"),
            "SAGE_CURL_BIN": str(bin_dir / "curl-stub"),
            "SAGE_TEST_COMMAND_LOG": str(command_log),
            "SAGE_EXPECTED_UID": str(os.getuid()),
        }
    )
    return subprocess.run(
        ["bash", str(project_dir / "scripts" / "deploy_remote.sh")],
        input=_deployment_payload(values),
        env=env,
        capture_output=True,
        check=False,
    )


def test_remote_deploy_keeps_secrets_out_of_env_and_process_arguments(tmp_path):
    project_dir = Path(__file__).resolve().parents[1]
    transfer_dir, deploy_dir, bin_dir, command_log = _prepare_deployment_stubs(tmp_path)
    unique = secrets.token_urlsafe(24)
    values = _deployment_values(unique)
    result = _run_remote_deploy(project_dir, values, transfer_dir, deploy_dir, bin_dir, command_log)

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert not transfer_dir.exists()
    assert stat.S_IMODE(deploy_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((deploy_dir / ".env").stat().st_mode) == 0o600
    assert stat.S_IMODE((deploy_dir / "secrets").stat().st_mode) == 0o700

    env_values = dotenv_values(deploy_dir / ".env")
    assert env_values["POSTGRES_USER"] == values["POSTGRES_USER"]
    assert env_values["POSTGRES_DB"] == values["POSTGRES_DB"]
    assert env_values["NEO4J_USER"] == values["NEO4J_USER"]
    assert env_values["SAGE_IMAGE"] == values["SAGE_IMAGE"]
    assert env_values["TEXT_PROVIDER"] == "openai"
    assert env_values["EMBEDDING_PROVIDER"] == "openai"

    secret_files = {
        "postgres_password": values["POSTGRES_PASSWORD"],
        "neo4j_auth": f"{values['NEO4J_USER']}/{values['NEO4J_PASSWORD']}",
        "neo4j_password": values["NEO4J_PASSWORD"],
        "openai_api_key": values["OPENAI_API_KEY"],
        "langsmith_api_key": values["LANGSMITH_API_KEY"],
        "sage_api_key": values["SAGE_API_KEY"],
        "sage_mcp_key": values["SAGE_MCP_KEY"],
        "sage_mcp_backend_key": values["SAGE_MCP_BACKEND_KEY"],
    }
    for name, expected in secret_files.items():
        path = deploy_dir / "secrets" / name
        assert path.read_text(encoding="utf-8") == expected
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not (deploy_dir / "secrets" / "openrouter_api_key").exists()

    public_artifacts = (deploy_dir / ".env").read_text(encoding="utf-8")
    public_artifacts += command_log.read_text(encoding="utf-8")
    for value in (*secret_files.values(), values["GHCR_TOKEN"]):
        if value:
            assert value not in public_artifacts
    commands = command_log.read_text(encoding="utf-8")
    assert "-f docker-compose.openai.yml" in commands
    assert "-f docker-compose.openrouter.yml" not in commands


@pytest.mark.parametrize(
    ("overrides", "expected_secret_files", "expected_overrides"),
    (
        (
            {
                "OPENAI_API_KEY": "",
                "TEXT_PROVIDER": "ollama",
                "EMBEDDING_PROVIDER": "ollama",
                "GRAPHITI_TEXT_PROVIDER": "ollama",
                "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
                "OLLAMA_BASE_URL": "http://ollama.internal:11434",
            },
            frozenset(),
            frozenset(),
        ),
        (
            {
                "OPENAI_API_KEY": "",
                "OPENROUTER_API_KEY": "openrouter-selected-secret",
                "TEXT_PROVIDER": "openrouter",
                "EMBEDDING_PROVIDER": "openrouter",
                "GRAPHITI_TEXT_PROVIDER": "openrouter",
                "GRAPHITI_EMBEDDING_PROVIDER": "openrouter",
                "OPENROUTER_CHAT_MODEL": "example/chat-model",
                "OPENROUTER_EMBEDDING_MODEL": "example/embedding-model",
            },
            frozenset({"openrouter_api_key"}),
            frozenset({"docker-compose.openrouter.yml"}),
        ),
        (
            {
                "OPENROUTER_API_KEY": "openrouter-selected-secret",
                "TEXT_PROVIDER": "openrouter",
                "EMBEDDING_PROVIDER": "openai",
                "GRAPHITI_TEXT_PROVIDER": "openrouter",
                "GRAPHITI_EMBEDDING_PROVIDER": "openai",
                "OPENROUTER_CHAT_MODEL": "example/chat-model",
            },
            frozenset({"openai_api_key", "openrouter_api_key"}),
            frozenset({"docker-compose.openai.yml", "docker-compose.openrouter.yml"}),
        ),
    ),
)
def test_remote_deploy_mounts_only_selected_cloud_provider_secrets(
    tmp_path: Path,
    overrides: dict[str, str],
    expected_secret_files: frozenset[str],
    expected_overrides: frozenset[str],
):
    project_dir = Path(__file__).resolve().parents[1]
    transfer_dir, deploy_dir, bin_dir, command_log = _prepare_deployment_stubs(tmp_path)
    values = _deployment_values(secrets.token_urlsafe(16), **overrides)

    result = _run_remote_deploy(project_dir, values, transfer_dir, deploy_dir, bin_dir, command_log)

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    commands = command_log.read_text(encoding="utf-8")
    for secret_name in ("openai_api_key", "openrouter_api_key"):
        assert (deploy_dir / "secrets" / secret_name).exists() == (
            secret_name in expected_secret_files
        )
    for override_name in ("docker-compose.openai.yml", "docker-compose.openrouter.yml"):
        assert (f"-f {override_name}" in commands) == (override_name in expected_overrides)

    public_artifacts = (deploy_dir / ".env").read_text(encoding="utf-8") + commands
    for secret_name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GHCR_TOKEN"):
        if values[secret_name]:
            assert values[secret_name] not in public_artifacts


def test_remote_deploy_rejects_missing_selected_openrouter_key(tmp_path: Path):
    project_dir = Path(__file__).resolve().parents[1]
    transfer_dir, deploy_dir, bin_dir, command_log = _prepare_deployment_stubs(tmp_path)
    values = _deployment_values(
        secrets.token_urlsafe(16),
        OPENAI_API_KEY="",
        OPENROUTER_API_KEY="",
        TEXT_PROVIDER="openrouter",
        EMBEDDING_PROVIDER="ollama",
        GRAPHITI_TEXT_PROVIDER="openrouter",
        GRAPHITI_EMBEDDING_PROVIDER="ollama",
        OPENROUTER_CHAT_MODEL="example/chat-model",
        OLLAMA_BASE_URL="http://ollama.internal:11434",
    )

    result = _run_remote_deploy(project_dir, values, transfer_dir, deploy_dir, bin_dir, command_log)

    assert result.returncode != 0
    assert b"OPENROUTER_API_KEY is required" in result.stderr
    assert not deploy_dir.exists()
    assert not command_log.exists()


def test_production_compose_mounts_cloud_secrets_only_through_provider_overrides():
    project_dir = Path(__file__).resolve().parents[1]
    base = yaml.safe_load((project_dir / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    api = base["services"]["api"]

    assert "OPENAI_API_KEY_FILE" not in api["environment"]
    assert "OPENROUTER_API_KEY_FILE" not in api["environment"]
    assert "openai_api_key" not in api["secrets"]
    assert "openrouter_api_key" not in api["secrets"]
    assert "openai_api_key" not in base["secrets"]
    assert "openrouter_api_key" not in base["secrets"]

    for provider in ("openai", "openrouter"):
        override = yaml.safe_load(
            (project_dir / f"docker-compose.{provider}.yml").read_text(encoding="utf-8")
        )
        secret_name = f"{provider}_api_key"
        file_variable = f"{provider.upper()}_API_KEY_FILE"
        assert override["services"]["api"]["environment"] == {
            file_variable: f"/run/secrets/{secret_name}"
        }
        assert override["services"]["api"]["secrets"] == [secret_name]
        assert override["secrets"][secret_name]["file"] == f"./secrets/{secret_name}"


def test_development_compose_preserves_openrouter_alias_as_a_distinct_input():
    project_dir = Path(__file__).resolve().parents[1]
    development = yaml.safe_load((project_dir / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = development["services"]["api"]["environment"]

    assert environment["OPENROUTER_API_KEY"] == "${OPENROUTER_API_KEY:-}"
    assert environment["OPENROUTER_KEY"] == "${OPENROUTER_KEY:-}"


def test_container_entrypoint_loads_secret_files_without_retaining_paths(tmp_path):
    project_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    expected_hashes = {}

    for name in SECRET_ENV_NAMES:
        value = f"{name.lower()}-{secrets.token_urlsafe(16)}"
        secret_file = tmp_path / name.lower()
        secret_file.write_text(value, encoding="utf-8")
        env[f"{name}_FILE"] = str(secret_file)
        env.pop(name, None)
        expected_hashes[name] = hashlib.sha256(value.encode()).hexdigest()

    probe = (
        "import hashlib,json,os;"
        f"names={SECRET_ENV_NAMES!r};"
        "assert all(name in os.environ for name in names);"
        "assert all(name + '_FILE' not in os.environ for name in names);"
        "print(json.dumps({name:hashlib.sha256(os.environ[name].encode()).hexdigest() "
        "for name in names},sort_keys=True))"
    )
    result = subprocess.run(
        [
            "bash",
            str(project_dir / "src" / "scripts" / "entrypoint.sh"),
            "python3",
            "-c",
            probe,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected_hashes
