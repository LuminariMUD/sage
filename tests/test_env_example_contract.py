"""Contract tests for the public environment template."""

from __future__ import annotations

import re
from pathlib import Path

from dotenv import dotenv_values

from src.llm.provider_config import (
    PROVIDER_ENVIRONMENT_FIELDS,
    PROVIDER_SECRET_FILE_FIELDS,
    PROVIDER_SECRET_VALUE_FIELDS,
    resolve_provider_settings,
)

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
SOURCE_ROOT = ENV_EXAMPLE.parent / "src"
ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
PYTHON_ENV_LOOKUP = re.compile(r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z][A-Z0-9_]*)["']""")

REQUIRED_RUNTIME_FIELDS = {
    "AGENT_TYPE",
    "ALLOWED_HOSTS",
    "ALLOWED_ORIGINS",
    "API_HOST",
    "API_PORT",
    "API_RELOAD",
    "API_WORKERS",
    "DISABLE_AUTH",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "ENABLE_REACT",
    "GRAPHITI_LLM_MODEL",
    "GRAPHITI_EMBEDDING_PROVIDER",
    "GRAPHITI_PROVIDER",
    "GRAPHITI_TEXT_PROVIDER",
    "GRAPHITI_TELEMETRY_ENABLED",
    "LANGCHAIN_CONFIDENCE_THRESHOLD",
    "LANGCHAIN_ENABLE_REFLECTION",
    "LANGCHAIN_INTERNAL_API_BASE",
    "LANGCHAIN_MAX_RETRIEVAL_ROUNDS",
    "LANGCHAIN_MODEL",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_REFLECTION_MODEL",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "LOG_FILE",
    "LOG_LEVEL",
    "LORE_DIR",
    "MCP_CORS_ORIGINS",
    "MCP_HOST",
    "MCP_PORT",
    "NEO4J_BOLT_PORT",
    "NEO4J_HTTP_PORT",
    "NEO4J_IMAGE",
    "NEO4J_PASSWORD",
    "NEO4J_URI",
    "NEO4J_USER",
    "OLLAMA_BASE_URL",
    "OLLAMA_CHAT_MODEL",
    "OLLAMA_EMBEDDING_BATCH_SIZE",
    "OLLAMA_EMBEDDING_MODEL",
    "OLLAMA_HOST_PORT",
    "OLLAMA_MAX_CONTEXT_TOKENS",
    "OLLAMA_REASONING_MODEL",
    "OLLAMA_REQUEST_TIMEOUT",
    "OLLAMA_TOOLS_MODEL",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_FILE",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_CHAT_MODEL",
    "OPENROUTER_EMBEDDING_DIMENSIONS",
    "OPENROUTER_EMBEDDING_MODEL",
    "OPENROUTER_KEY",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_IMAGE",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "ROOT_PATH",
    "SAGE_API_KEY",
    "SAGE_CURL_BIN",
    "SAGE_DEPLOY_DIR",
    "SAGE_DOCKER_BIN",
    "SAGE_EXPECTED_UID",
    "SAGE_IMAGE",
    "SAGE_MCP_BACKEND_KEY",
    "SAGE_MCP_KEY",
    "SAGE_SENTENCE_TRANSFORMERS_REVISION",
    "SAGE_TRANSFER_DIR",
    "TEXT_PROVIDER",
    "USE_LEGACY_LANGCHAIN",
    "USE_LOCAL_EMBEDDINGS",
    "UVICORN_LOG_LEVEL",
} | PROVIDER_ENVIRONMENT_FIELDS

PUBLIC_SECRET_FIELDS = {
    "LANGSMITH_API_KEY",
    "NEO4J_PASSWORD",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_KEY",
    "POSTGRES_PASSWORD",
    "SAGE_API_KEY",
    "SAGE_MCP_BACKEND_KEY",
    "SAGE_MCP_KEY",
} | PROVIDER_SECRET_VALUE_FIELDS


def _assignments() -> list[tuple[str, str]]:
    assignments = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if match := ASSIGNMENT.fullmatch(line):
            assignments.append((match.group(1), match.group(2)))
    return assignments


def test_env_example_has_complete_unique_runtime_fields():
    assignments = _assignments()
    names = [name for name, _ in assignments]

    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"duplicate .env.example fields: {duplicates}"

    missing = sorted(REQUIRED_RUNTIME_FIELDS - set(names))
    assert not missing, f"missing .env.example runtime fields: {missing}"

    assert "CORS_ORIGINS" not in names, "runtime uses ALLOWED_ORIGINS"


def test_env_example_never_contains_secret_placeholders():
    values = dict(_assignments())
    populated_secrets = sorted(name for name in PUBLIC_SECRET_FIELDS if values.get(name))
    assert not populated_secrets, f"public template contains secret values: {populated_secrets}"

    # A production image must be supplied as an immutable digest by deployment tooling.
    assert values["SAGE_IMAGE"] == ""


def test_env_example_documents_provider_secret_file_transport():
    values = dict(_assignments())

    assert all(values[name] == "" for name in PROVIDER_SECRET_VALUE_FIELDS)
    assert all(values[name] == "" for name in PROVIDER_SECRET_FILE_FIELDS)
    assert "OPENROUTER_KEY_FILE" not in values


def test_env_example_default_provider_profile_resolves_without_cloud_secrets():
    environment = {name: value or "" for name, value in dotenv_values(ENV_EXAMPLE).items()}

    settings = resolve_provider_settings(environment)

    assert settings.text_provider == "ollama"
    assert settings.embedding_provider == "ollama"
    assert settings.graphiti_text_provider == "ollama"
    assert settings.graphiti_embedding_provider == "ollama"
    assert settings.text_route("chat").primary.connection.api_key is None
    assert settings.embedding_profile.connection.api_key is None


def test_env_example_covers_literal_python_environment_lookups():
    declared_names = {name for name, _ in _assignments()}
    source_names = set()

    for path in SOURCE_ROOT.rglob("*.py"):
        source_names.update(PYTHON_ENV_LOOKUP.findall(path.read_text(encoding="utf-8")))

    # XDG_STATE_HOME is a standard process-level override, not Sage configuration.
    missing = sorted(source_names - declared_names - {"XDG_STATE_HOME"})
    assert not missing, f"Python runtime fields missing from .env.example: {missing}"
