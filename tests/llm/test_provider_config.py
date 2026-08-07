"""Unit coverage for the provider-neutral configuration contract."""

from __future__ import annotations

import logging

import pytest

from src.llm.provider_config import ProviderSettingsResolver, resolve_provider_settings


def _ollama_environment() -> dict[str, str]:
    return {
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://ollama:11434/",
        "OLLAMA_CHAT_MODEL": "qwen2.5:7b",
        "OLLAMA_CREATIVE_MODEL": "qwen2.5:7b",
        "OLLAMA_REASONING_MODEL": "qwen2.5:3b",
        "OLLAMA_EXTRACTION_MODEL": "qwen2.5:3b",
        "OLLAMA_TOOLS_MODEL": "qwen2.5:7b",
        "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
        "OLLAMA_EMBEDDING_DIMENSIONS": "768",
    }


def _openrouter_environment() -> dict[str, str]:
    return {
        "OPENROUTER_API_KEY": "unit-test-openrouter-secret",
        "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENROUTER_SITE_URL": "https://sage.example.test",
        "OPENROUTER_APP_NAME": "Luminari Sage Tests",
        "OPENROUTER_CHAT_MODEL": "qwen/qwen3-test",
        "OPENROUTER_CREATIVE_MODEL": "anthropic/claude-test",
        "OPENROUTER_REASONING_MODEL": "openai/reasoning-test",
        "OPENROUTER_EXTRACTION_MODEL": "qwen/qwen3-test",
        "OPENROUTER_TOOLS_MODEL": "openai/tool-test",
        "OPENROUTER_EMBEDDING_MODEL": "perplexity/pplx-embed-test",
        "OPENROUTER_EMBEDDING_DIMENSIONS": "1024",
    }


def test_all_ollama_resolves_without_any_cloud_key():
    settings = resolve_provider_settings(_ollama_environment())

    assert settings.text_provider == "ollama"
    assert settings.embedding_provider == "ollama"
    assert settings.graphiti_text_provider == "ollama"
    assert settings.graphiti_embedding_provider == "ollama"
    assert settings.text_route("chat").primary.model == "qwen2.5:7b"
    assert settings.embedding_profile.dimensions == 768
    assert settings.embedding_profile.connection.api_key is None


def test_resolver_refuses_undeclared_environment_field_access():
    resolver = ProviderSettingsResolver({})

    with pytest.raises(RuntimeError, match="Provider environment field is undeclared"):
        resolver._value("OPENROUTER_API_KEEY")


@pytest.mark.parametrize(
    ("text_provider", "embedding_provider"),
    [
        ("ollama", "ollama"),
        ("ollama", "openrouter"),
        ("openrouter", "ollama"),
        ("openrouter", "openrouter"),
    ],
)
def test_all_primary_provider_combinations_resolve(text_provider, embedding_provider):
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = text_provider
    environment["EMBEDDING_PROVIDER"] = embedding_provider

    settings = resolve_provider_settings(environment)

    assert settings.text_provider == text_provider
    assert settings.embedding_provider == embedding_provider
    assert settings.text_route("tools").primary.connection.provider == text_provider
    assert settings.embedding_profile.connection.provider == embedding_provider


def test_unselected_openrouter_does_not_require_a_key_or_validate_its_settings():
    environment = _ollama_environment()
    environment["OPENROUTER_BASE_URL"] = "not a url"

    settings = resolve_provider_settings(environment)

    assert settings.text_provider == "ollama"
    assert settings.embedding_provider == "ollama"


def test_selected_openrouter_requires_credentials():
    environment = _ollama_environment()
    environment["TEXT_PROVIDER"] = "openrouter"
    environment["OPENROUTER_CHAT_MODEL"] = "qwen/qwen3-test"

    with pytest.raises(ValueError, match="OpenRouter credentials are required"):
        resolve_provider_settings(environment)


def test_openrouter_key_legacy_alias_is_supported_without_logging_secret(caplog):
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"
    environment["OPENROUTER_KEY"] = environment.pop("OPENROUTER_API_KEY")

    with caplog.at_level(logging.WARNING):
        settings = resolve_provider_settings(environment)

    assert settings.text_route("chat").primary.connection.api_key is not None
    assert "OPENROUTER_KEY is deprecated" in caplog.text
    assert "unit-test-openrouter-secret" not in caplog.text


def test_openrouter_key_file_is_read_only_when_selected(tmp_path):
    secret_file = tmp_path / "openrouter-key"
    secret_file.write_text("file-backed-test-secret\n", encoding="utf-8")
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"
    environment.pop("OPENROUTER_API_KEY")
    environment["OPENROUTER_API_KEY_FILE"] = str(secret_file)

    settings = resolve_provider_settings(environment)

    secret = settings.text_route("chat").primary.connection.api_key
    assert secret is not None
    assert secret.get_secret_value() == "file-backed-test-secret"
    assert "file-backed-test-secret" not in str(settings.sanitized_summary())


def test_new_and_legacy_openrouter_keys_are_rejected_together():
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"
    environment["OPENROUTER_KEY"] = "legacy-secret"

    with pytest.raises(ValueError, match="Configure OPENROUTER_KEY only"):
        resolve_provider_settings(environment)


def test_openrouter_connection_builds_only_optional_attribution_headers():
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"

    connection = resolve_provider_settings(environment).text_route("chat").primary.connection

    assert connection.base_url == "https://openrouter.ai/api/v1"
    assert connection.default_headers == {
        "HTTP-Referer": "https://sage.example.test",
        "X-OpenRouter-Title": "Luminari Sage Tests",
    }
    assert "Authorization" not in connection.default_headers


def test_openrouter_routing_defaults_fail_closed_for_privacy_and_fallback():
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"
    environment["EMBEDDING_PROVIDER"] = "openrouter"

    settings = resolve_provider_settings(environment)

    text_policy = settings.text_route("chat").primary.routing
    embedding_policy = settings.embedding_profile.routing
    assert text_policy is not None
    assert embedding_policy is not None
    assert text_policy.as_request_body() == {
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
    }
    assert embedding_policy.allow_fallbacks is False


def test_openrouter_prompt_profile_uses_model_family_not_transport():
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"

    settings = resolve_provider_settings(environment)

    assert settings.text_route("chat").primary.prompt_profile == "qwen"
    assert settings.text_route("creative").primary.prompt_profile == "claude"
    assert settings.text_route("reasoning").primary.prompt_profile == "openai"


def test_graphiti_provider_overrides_are_independent():
    environment = _ollama_environment() | _openrouter_environment()
    environment["GRAPHITI_TEXT_PROVIDER"] = "openrouter"
    environment["GRAPHITI_EMBEDDING_PROVIDER"] = "ollama"
    environment["OPENROUTER_GRAPHITI_MODEL"] = "qwen/graph-extractor-test"

    settings = resolve_provider_settings(environment)

    assert settings.text_provider == "ollama"
    assert settings.embedding_provider == "ollama"
    assert settings.graphiti_text_provider == "openrouter"
    assert settings.graphiti_embedding_provider == "ollama"
    assert settings.graphiti_text_route.primary.model == "qwen/graph-extractor-test"
    assert settings.graphiti_embedding_profile.model == "nomic-embed-text"


def test_openrouter_graphiti_capacity_is_independent_from_local_defaults():
    openrouter_environment = _ollama_environment() | _openrouter_environment()
    openrouter_environment["TEXT_PROVIDER"] = "openrouter"
    openrouter_environment["GRAPHITI_TEXT_PROVIDER"] = "openrouter"
    openrouter = resolve_provider_settings(openrouter_environment)
    local = resolve_provider_settings(_ollama_environment())

    assert openrouter.text_route("chat").primary.context_limit == 1_000_000
    assert openrouter.graphiti_text_route.primary.context_limit == 1_000_000
    assert openrouter.graphiti_text_route.primary.max_output_tokens == 65_536
    assert openrouter.graphiti_text_route.primary.maximum_model_attempts == 3
    assert openrouter.graphiti_text_route.maximum_provider_calls == 16
    assert openrouter.graph_sync_policy.max_provider_calls == 16

    assert local.text_route("chat").primary.context_limit == 12_288
    assert local.graphiti_text_route.primary.max_output_tokens == 4096
    assert local.graphiti_text_route.primary.maximum_model_attempts == 2
    assert local.graphiti_text_route.maximum_provider_calls == 32


def test_ollama_extraction_defaults_to_tool_capable_chat_model():
    environment = _ollama_environment()
    environment.pop("OLLAMA_EXTRACTION_MODEL")

    settings = resolve_provider_settings(environment)

    assert settings.text_route("extraction").primary.model == "qwen2.5:7b"
    assert settings.graphiti_text_route.primary.model == "qwen2.5:7b"


def test_openrouter_graphiti_capacity_overrides_are_resolved_together():
    environment = _ollama_environment() | _openrouter_environment()
    environment.update(
        {
            "GRAPHITI_TEXT_PROVIDER": "openrouter",
            "OPENROUTER_MAX_CONTEXT_TOKENS": "750000",
            "OPENROUTER_GRAPHITI_MAX_OUTPUT_TOKENS": "32768",
            "OPENROUTER_GRAPHITI_PRIMARY_ATTEMPTS": "4",
            "OPENROUTER_GRAPHITI_MAX_PROVIDER_CALLS": "20",
        }
    )

    settings = resolve_provider_settings(environment)

    assert settings.graphiti_text_route.primary.context_limit == 750_000
    assert settings.graphiti_text_route.primary.max_output_tokens == 32_768
    assert settings.graphiti_text_route.primary.maximum_model_attempts == 4
    assert settings.graphiti_text_route.maximum_provider_calls == 20
    assert settings.graph_sync_policy.max_provider_calls == 20


def test_graphiti_explicit_fallback_is_ordered_and_bounded():
    environment = _ollama_environment()
    environment.update(
        {
            "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "ollama",
            "GRAPHITI_EXTRACTION_FALLBACK_MODEL": "qwen2.5:7b",
            "GRAPHITI_EXTRACTION_PRIMARY_ATTEMPTS": "2",
            "GRAPHITI_EXTRACTION_FALLBACK_ATTEMPTS": "1",
            "GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS": "3",
            "GRAPH_SYNC_MAX_PROVIDER_CALLS": "3",
        }
    )

    route = resolve_provider_settings(environment).graphiti_text_route

    assert [candidate.model for candidate in route.candidates] == [
        "qwen2.5:3b",
        "qwen2.5:7b",
    ]
    assert route.maximum_provider_calls == 3
    assert route.fallback_on == {
        "malformed_json",
        "schema_validation",
        "output_limit",
    }


def test_graphiti_route_and_durable_provider_call_limits_cannot_conflict():
    environment = _ollama_environment()
    environment["GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS"] = "2"
    environment["GRAPH_SYNC_MAX_PROVIDER_CALLS"] = "3"

    with pytest.raises(ValueError, match="must match"):
        resolve_provider_settings(environment)


def test_fingerprints_are_stable_and_do_not_encode_credentials():
    first_environment = _ollama_environment() | _openrouter_environment()
    first_environment["TEXT_PROVIDER"] = "openrouter"
    second_environment = dict(first_environment)
    second_environment["OPENROUTER_API_KEY"] = "a-different-secret"

    first = resolve_provider_settings(first_environment).text_route("chat").primary
    second = resolve_provider_settings(second_environment).text_route("chat").primary

    assert first.fingerprint == second.fingerprint
    assert "unit-test-openrouter-secret" not in first.fingerprint
    assert first.connection.cache_identity() != second.connection.cache_identity()


def test_legacy_selector_precedence_warns_and_never_aliases_openai_to_openrouter(caplog):
    environment = {
        "LLM_PROVIDER": "openai",
        "USE_LOCAL_EMBEDDINGS": "false",
        "OPENAI_API_KEY": "direct-openai-test-secret",
    }

    with caplog.at_level(logging.WARNING):
        settings = resolve_provider_settings(environment)

    assert settings.text_provider == "openai"
    assert settings.embedding_provider == "openai"
    assert settings.graphiti_text_provider == "openai"
    assert settings.graphiti_embedding_provider == "openai"
    assert "LLM_PROVIDER is deprecated" in caplog.text
    assert "direct-openai-test-secret" not in caplog.text


def test_new_selectors_take_precedence_over_legacy_values():
    environment = _ollama_environment()
    environment.update(
        {
            "LLM_PROVIDER": "openai",
            "USE_LOCAL_EMBEDDINGS": "false",
            "OPENAI_API_KEY": "unused-direct-openai-secret",
        }
    )

    settings = resolve_provider_settings(environment)

    assert settings.text_provider == "ollama"
    assert settings.embedding_provider == "ollama"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("OPENROUTER_BASE_URL", "http://openrouter.invalid/v1", "must use HTTPS"),
        ("OPENROUTER_EMBEDDING_DIMENSIONS", "0", "must be between"),
        ("OPENROUTER_TEXT_DATA_COLLECTION", "maybe", "must be allow or deny"),
    ],
)
def test_selected_openrouter_settings_are_strictly_validated(name, value, message):
    environment = _ollama_environment() | _openrouter_environment()
    environment["TEXT_PROVIDER"] = "openrouter"
    environment["EMBEDDING_PROVIDER"] = "openrouter"
    environment[name] = value

    with pytest.raises(ValueError, match=message):
        resolve_provider_settings(environment)
