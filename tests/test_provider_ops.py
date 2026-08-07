"""Offline tests for provider configuration checks and guarded probes."""

from __future__ import annotations

from argparse import Namespace

import pytest

from src.llm.provider_config import resolve_provider_settings
from src.scripts import provider_ops


def _ollama_settings():
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_REASONING_MODEL": "local/reasoning",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OLLAMA_EMBEDDING_DIMENSIONS": "3",
        }
    )


def _args(command: str, **overrides: object) -> Namespace:
    values = {
        "command": command,
        "json": False,
        "confirm": provider_ops.PROBE_CONFIRMATION,
        "task": "chat",
        "scope": "application",
    }
    values.update(overrides)
    return Namespace(**values)


def test_configuration_report_exposes_only_boolean_credential_state():
    secret = "offline-openrouter-secret"
    settings = resolve_provider_settings(
        {
            "TEXT_PROVIDER": "openrouter",
            "EMBEDDING_PROVIDER": "openrouter",
            "GRAPHITI_TEXT_PROVIDER": "openrouter",
            "GRAPHITI_EMBEDDING_PROVIDER": "openrouter",
            "OPENROUTER_KEY": secret,
            "OPENROUTER_CHAT_MODEL": "example/chat",
            "OPENROUTER_EMBEDDING_MODEL": "example/embed",
        }
    )

    report = provider_ops.configuration_report(settings)

    assert report["status"] == "valid"
    assert report["credential_status"] == {"openrouter": True}
    assert secret not in str(report)


@pytest.mark.asyncio
async def test_probe_refusal_happens_before_configuration_resolution(capsys):
    resolved = False

    def resolver():
        nonlocal resolved
        resolved = True
        raise AssertionError("resolver must remain unused")

    result = await provider_ops.run(
        _args("text-probe", confirm="wrong"),
        settings_resolver=resolver,
    )

    assert result == 2
    assert resolved is False
    assert provider_ops.PROBE_CONFIRMATION in capsys.readouterr().err


@pytest.mark.asyncio
async def test_text_probe_makes_one_bounded_call_without_emitting_content():
    calls = []

    class FakeProvider:
        last_response_metadata = {
            "actual_model": "local/chat",
            "upstream_provider": "offline-test",
            "usage": {"completion_tokens": 1},
        }

        async def generate(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            return "sensitive probe response"

    def factory(candidate):
        assert candidate.connection.transport_retry.maximum_attempts == 1
        assert candidate.maximum_model_attempts == 1
        return FakeProvider()

    report = await provider_ops.execute_text_probe(
        _ollama_settings(),
        "chat",
        provider_factory=factory,
    )

    assert len(calls) == 1
    assert calls[0][0] == provider_ops.TEXT_PROBE_INPUT
    assert report["status"] == "passed"
    assert report["actual_model"] == "local/chat"
    assert "sensitive probe response" not in str(report)
    assert provider_ops.TEXT_PROBE_INPUT not in str(report)


@pytest.mark.asyncio
async def test_embedding_probe_validates_shape_without_emitting_vector():
    class FakeEmbedder:
        async def embed_text(self, text):
            assert text == provider_ops.EMBEDDING_PROBE_INPUT
            return [0.5, -0.25, 0.75]

        def sanitized_metadata(self):
            return {"transport_attempts": 1, "usage": {"prompt_tokens": 2}}

    report = await provider_ops.execute_embedding_probe(
        _ollama_settings(),
        "application",
        embedder_factory=lambda profile: FakeEmbedder(),
    )

    assert report["status"] == "passed"
    assert report["dimensions"] == 3
    assert "0.5" not in str(report)
    assert provider_ops.EMBEDDING_PROBE_INPUT not in str(report)


@pytest.mark.asyncio
async def test_cloud_embedding_probe_disables_adapter_retries(monkeypatch):
    settings = resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "openrouter",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "offline-openrouter-secret",
            "OPENROUTER_EMBEDDING_MODEL": "example/embed",
            "OPENROUTER_EMBEDDING_DIMENSIONS": "3",
        }
    )
    retries = []

    class FakeEmbedder:
        async def embed_text(self, text):
            return [0.5, -0.25, 0.75]

    def factory(profile, *, transport_max_retries=None):
        retries.append(transport_max_retries)
        return FakeEmbedder()

    monkeypatch.setattr(provider_ops, "create_embedder", factory)

    report = await provider_ops.execute_embedding_probe(settings, "application")

    assert report["status"] == "passed"
    assert retries == [0]


@pytest.mark.asyncio
async def test_embedding_probe_rejects_profile_dimension_mismatch():
    class FakeEmbedder:
        async def embed_text(self, text):
            return [1.0, 2.0]

    with pytest.raises(ValueError, match="dimension"):
        await provider_ops.execute_embedding_probe(
            _ollama_settings(),
            "application",
            embedder_factory=lambda profile: FakeEmbedder(),
        )


@pytest.mark.asyncio
async def test_probe_failure_output_omits_exception_and_secret_details(capsys):
    async def failed_probe(settings, task):
        raise RuntimeError("offline-openrouter-secret prompt and response")

    result = await provider_ops.run(
        _args("text-probe"),
        settings_resolver=_ollama_settings,
        text_probe=failed_probe,
    )

    output = capsys.readouterr().err
    assert result == 1
    assert "offline-openrouter-secret" not in output
    assert "prompt and response" not in output
    assert "failure_class" not in output


@pytest.mark.asyncio
async def test_configuration_check_never_invokes_probe_runners(capsys):
    async def unexpected(*args):
        raise AssertionError("probe runner must remain unused")

    result = await provider_ops.run(
        _args("check"),
        settings_resolver=_ollama_settings,
        text_probe=unexpected,
        embedding_probe=unexpected,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "Provider configuration: VALID" in output
    assert "not-required" in output
