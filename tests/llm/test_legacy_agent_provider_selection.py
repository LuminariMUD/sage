"""Legacy agent constructors must default to the shared text-provider routes."""

from __future__ import annotations

import importlib
import inspect

import pytest


class _FakeAgent:
    def __init__(self, model, **kwargs):
        self.model = model
        self.kwargs = kwargs

    def tool(self, function):
        return function


@pytest.mark.parametrize(
    ("module_name", "class_name", "expected_tasks"),
    [
        ("src.agents.lore_chat_agent", "LoreChatAgent", ["extraction", "chat"]),
        ("src.agents.lore_chat_agent_v2", "EnhancedLoreChatAgent", ["tools"]),
        ("src.agents.lore_chat_agent_v3", "LuminariLoreChatAgent", ["tools"]),
        ("src.agents.lore_chat_agent_final", "FinalLoreChatAgent", ["tools"]),
        ("src.agents.lore_chat_agent_simple", "SimpleLoreChatAgent", ["tools"]),
        ("src.agents.lore_chat_agent_streaming", "StreamingLoreChatAgent", ["tools"]),
        ("src.agents.lore_chat_agent_structured", "StructuredLoreChatAgent", ["tools"]),
    ],
)
def test_legacy_chat_agents_need_no_openai_key(
    monkeypatch,
    module_name: str,
    class_name: str,
    expected_tasks: list[str],
):
    module = importlib.import_module(module_name)
    calls = []

    def fake_create_text_model(task="chat", **kwargs):
        calls.append((task, kwargs))
        return object()

    monkeypatch.setattr(module, "Agent", _FakeAgent)
    monkeypatch.setattr(module, "create_text_model", fake_create_text_model)

    agent_class = getattr(module, class_name)
    signature = inspect.signature(agent_class)
    assert signature.parameters["openai_api_key"].default is None

    agent_class()

    assert [task for task, _ in calls] == expected_tasks
    assert all(call["legacy_openai_api_key"] is None for _, call in calls)


def test_base_validator_defaults_to_extraction_route(monkeypatch):
    module = importlib.import_module("src.agents.base_validator")
    calls = []

    def fake_create_text_model(task="chat", **kwargs):
        calls.append((task, kwargs))
        return object()

    monkeypatch.setattr(module, "Agent", _FakeAgent)
    monkeypatch.setattr(module, "create_text_model", fake_create_text_model)

    validator = module.BaseValidator("test-validator")

    assert validator.agent_id == "test-validator"
    assert calls == [
        (
            "extraction",
            {
                "legacy_openai_api_key": None,
                "legacy_openai_model": "gpt-4o-mini",
            },
        )
    ]


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [
        ("src.agents.relationship_validator", "RelationshipValidator"),
        ("src.agents.relationship_corrector", "RelationshipCorrector"),
    ],
)
def test_relationship_agents_keep_only_an_optional_legacy_key(
    module_name: str,
    class_name: str,
):
    agent_class = getattr(importlib.import_module(module_name), class_name)

    assert inspect.signature(agent_class).parameters["openai_api_key"].default is None
