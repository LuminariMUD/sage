"""Regression coverage for production secret-file deployment."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path

from dotenv import dotenv_values

SECRET_ENV_NAMES = (
    "POSTGRES_PASSWORD",
    "NEO4J_PASSWORD",
    "OPENAI_API_KEY",
    "LANGSMITH_API_KEY",
    "SAGE_API_KEY",
    "SAGE_MCP_KEY",
    "SAGE_MCP_BACKEND_KEY",
)


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_remote_deploy_keeps_secrets_out_of_env_and_process_arguments(tmp_path):
    project_dir = Path(__file__).resolve().parents[1]
    transfer_dir = tmp_path / "transfer"
    deploy_dir = tmp_path / "deploy"
    bin_dir = tmp_path / "bin"
    command_log = tmp_path / "commands.log"
    transfer_dir.mkdir()
    bin_dir.mkdir()
    (transfer_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (transfer_dir / "postgresql_schema.sql").write_text("SELECT 1;\n", encoding="utf-8")

    _write_executable(
        bin_dir / "docker-stub",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$SAGE_TEST_COMMAND_LOG"
if [[ "${1:-}" == "login" ]]; then
    read -r _ || true
fi
""",
    )
    _write_executable(bin_dir / "curl-stub", "#!/usr/bin/env bash\nexit 0\n")

    unique = secrets.token_urlsafe(24)
    values = [
        "app_user",
        f"pg '$ {unique} \\\\ value",
        "app_db",
        "neo4j",
        f"neo '$ {unique} \\\\ value",
        f"openai-{unique}",
        "",
        f"api-{unique}",
        f"mcp-{unique}",
        f"backend-{unique}",
        "ci-actor",
        f"registry-{unique}",
        "ghcr.io/luminarimud/sage@sha256:" + ("a" * 64),
    ]
    payload = b"\0".join(value.encode() for value in values) + b"\0"
    env = {
        **os.environ,
        "SAGE_TRANSFER_DIR": str(transfer_dir),
        "SAGE_DEPLOY_DIR": str(deploy_dir),
        "SAGE_DOCKER_BIN": str(bin_dir / "docker-stub"),
        "SAGE_CURL_BIN": str(bin_dir / "curl-stub"),
        "SAGE_TEST_COMMAND_LOG": str(command_log),
        "SAGE_EXPECTED_UID": str(os.getuid()),
    }

    result = subprocess.run(
        ["bash", str(project_dir / "scripts" / "deploy_remote.sh")],
        input=payload,
        env=env,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert not transfer_dir.exists()
    assert stat.S_IMODE(deploy_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((deploy_dir / ".env").stat().st_mode) == 0o600
    assert stat.S_IMODE((deploy_dir / "secrets").stat().st_mode) == 0o700

    env_values = dotenv_values(deploy_dir / ".env")
    assert env_values["POSTGRES_USER"] == values[0]
    assert env_values["POSTGRES_DB"] == values[2]
    assert env_values["NEO4J_USER"] == values[3]
    assert env_values["SAGE_IMAGE"] == values[-1]

    secret_files = {
        "postgres_password": values[1],
        "neo4j_auth": f"{values[3]}/{values[4]}",
        "neo4j_password": values[4],
        "openai_api_key": values[5],
        "langsmith_api_key": values[6],
        "sage_api_key": values[7],
        "sage_mcp_key": values[8],
        "sage_mcp_backend_key": values[9],
    }
    for name, expected in secret_files.items():
        path = deploy_dir / "secrets" / name
        assert path.read_text(encoding="utf-8") == expected
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    public_artifacts = (deploy_dir / ".env").read_text(encoding="utf-8")
    public_artifacts += command_log.read_text(encoding="utf-8")
    for value in (*secret_files.values(), values[11]):
        if value:
            assert value not in public_artifacts


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
