"""Integration coverage for the current LangChain chat SSE path."""

import json

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class DummyChatService:
    """Provider-free service double that follows the current event contract."""

    async def stream_chat(self, message, conversation_history=None):
        assert message
        assert isinstance(conversation_history, list)
        yield {"type": "route", "route": "lore_query", "confidence": 1.0}
        yield {"type": "token", "content": "STREAMED ANSWER"}
        yield {
            "type": "final",
            "content": "STREAMED ANSWER",
            "route": "lore_query",
            "confidence": 1.0,
        }


@pytest.fixture(autouse=True)
def patch_chat_service(monkeypatch):
    from src.agents.langchain import service_selector

    monkeypatch.setattr(service_selector, "get_chat_service", lambda: DummyChatService())


def test_langchain_lore_query_stream(api_client):
    # initiate conversation with engine=langchain
    r = api_client.post(
        "/api/v1/chat/message", json={"message": "Tell me about dragons", "engine": "langchain"}
    )
    assert r.status_code == 200
    stream_url = r.json()["stream_url"]
    # consume stream
    events = []
    with api_client.stream("GET", stream_url) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                events.append(payload)
                if payload.get("type") == "final":
                    break
    routes = [e for e in events if e.get("type") == "route"]
    assert routes
    final = next(e for e in events if e.get("type") == "final")
    assert final["content"] == "STREAMED ANSWER"


def test_langchain_quest_plan(api_client):
    r = api_client.post(
        "/api/v1/chat/message",
        json={"message": "Generate quest arc about the ancient vault", "engine": "langchain"},
    )
    assert r.status_code == 200
    stream_url = r.json()["stream_url"]
    s = api_client.get(stream_url)
    # Non-streaming route returns single final event
    assert s.status_code == 200


def test_langchain_trace_flag(api_client):
    r = api_client.post(
        "/api/v1/chat/message", json={"message": "Tell me about plains", "engine": "langchain"}
    )
    stream_url = r.json()["stream_url"]
    saw_trace = False
    with api_client.stream("GET", stream_url + "?trace=1") as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("type") == "trace":
                    saw_trace = True
                    break
    assert saw_trace
