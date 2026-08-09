"""Regression coverage for selecting the current ReAct chat service."""

from src.agents.langchain import service_selector
from src.agents.langchain.legacy_service import LangChainChatService as LegacyChatService


def test_service_selector_prefers_react_when_tool_profile_is_ready(monkeypatch):
    selected_service = object()
    constructor_arguments = {}

    def build_react_service(**kwargs):
        constructor_arguments.update(kwargs)
        return selected_service

    from src.agents.langchain import react_service

    monkeypatch.setenv("USE_LEGACY_LANGCHAIN", "false")
    monkeypatch.setenv("ENABLE_REACT", "true")
    monkeypatch.setenv("LANGCHAIN_MODEL", "test-model")
    monkeypatch.setattr(service_selector, "text_profile_is_ready", lambda capability: True)
    monkeypatch.setattr(react_service, "ReactService", build_react_service)

    service = service_selector.get_chat_service()

    assert service is selected_service
    assert constructor_arguments == {
        "model_name": "test-model",
        "temperature": 0.7,
        "max_iterations": 20,
    }


def test_service_selector_falls_back_when_tool_profile_is_unready(monkeypatch):
    monkeypatch.setenv("USE_LEGACY_LANGCHAIN", "false")
    monkeypatch.setattr(service_selector, "text_profile_is_ready", lambda capability: False)

    service = service_selector.get_chat_service()

    assert isinstance(service, LegacyChatService)


def test_service_selector_honors_explicit_legacy_request(monkeypatch):
    monkeypatch.setattr(service_selector, "text_profile_is_ready", lambda capability: True)

    service = service_selector.get_chat_service(force_legacy=True)

    assert isinstance(service, LegacyChatService)
