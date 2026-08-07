"""Regression tests for the fully local LangChain service selection path."""

import sys
from types import ModuleType

import pytest

from src.agents.langchain.service_selector import get_chat_service


def test_ollama_react_service_does_not_require_openai_key(monkeypatch):
    """Ollama mode must not fall back merely because no cloud key exists."""

    class FakeReactService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = ModuleType("src.agents.langchain.react_service")
    fake_module.ReactService = FakeReactService

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("ENABLE_REACT", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)

    service = get_chat_service()

    assert isinstance(service, FakeReactService)


def test_openrouter_react_service_uses_shared_readiness(monkeypatch):
    """OpenRouter selection must not be gated on a direct OpenAI credential."""

    class FakeReactService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = ModuleType("src.agents.langchain.react_service")
    fake_module.ReactService = FakeReactService

    monkeypatch.setenv("TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-unit-test-secret")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "qwen/qwen-test")
    monkeypatch.setenv("ENABLE_REACT", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)

    service = get_chat_service()

    assert isinstance(service, FakeReactService)


def test_react_tool_selection_uses_non_streaming_model(monkeypatch):
    """Provider tool routing must not require a combined tools+stream endpoint."""
    from src.agents.langchain import react_service

    calls = []

    class FakeModel:
        def bind_tools(self, tools):
            self.tools = tools
            return self

    def fake_get_chat_model(**kwargs):
        calls.append(kwargs)
        return FakeModel()

    monkeypatch.setattr(react_service, "get_chat_model", fake_get_chat_model)
    monkeypatch.setattr(react_service, "get_focused_tools", list)

    react_service.ReactService()

    tools_call = next(call for call in calls if call["task"] == "tools")
    assert tools_call["streaming"] is False
    assert tools_call["disable_streaming"] is True
    assert tools_call["reasoning_effort"] == "none"
    assert "max_tokens" not in tools_call


@pytest.mark.asyncio
async def test_react_answer_tool_uses_normalized_retrieved_context(monkeypatch):
    """Model-supplied context cannot override the canonical retrieval state."""
    from src.agents.langchain import react_service

    captured = {}

    class FakeModel:
        def bind_tools(self, tools):
            return self

    class FakeAnswerTool:
        name = "answer_lore_question"

        async def ainvoke(self, arguments):
            captured.update(arguments)
            return {"answer": "grounded"}

    monkeypatch.setattr(react_service, "get_chat_model", lambda **kwargs: FakeModel())
    monkeypatch.setattr(react_service, "get_focused_tools", lambda: [FakeAnswerTool()])

    service = react_service.ReactService()
    state = {
        "request_intent": "informational",
        "current_step": {
            "tool_calls": [
                {
                    "name": "answer_lore_question",
                    "args": {
                        "question": "Planner paraphrase that lost the requested format",
                        "context": "invalid model value",
                    },
                }
            ]
        },
        "context_blocks": ["First fact", {"text": "Second fact"}],
        "original_request": "Answer in one concise sentence: What changed?",
        "tool_history": [],
        "created_content": [],
        "iteration_count": 0,
    }

    result = await service._act_step(state)

    assert captured == {
        "question": "Answer in one concise sentence: What changed?",
        "context": ["First fact", "Second fact"],
    }
    assert result["created_content"] == [
        {
            "type": "answer_lore_question",
            "content": {"answer": "grounded"},
            "iteration": 0,
        }
    ]
    result.update(
        {
            "max_iterations": 20,
            "current_step": {"result": {"answer": "grounded"}},
            "original_request": "Answer in one concise sentence: What changed?",
        }
    )
    assert service._should_continue(result) == "finalize"
