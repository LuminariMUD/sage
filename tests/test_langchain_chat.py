"""Tests for LangChain chat engine streaming and structured outputs.

These tests mock underlying OpenAI calls by monkeypatching ChatOpenAI.invoke/stream to avoid network.
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class DummyChunk:
    def __init__(self, content):
        self.content = content


class DummyLLM:
    def __init__(self, *a, **k):
        pass

    def invoke(self, messages):
        # Return simple deterministic content depending on last user message snippet
        last = messages[-1][1] if isinstance(messages[-1], tuple) else ""
        if "Generate quest" in last:
            return DummyChunk(
                '{"objective":"Test Obj","premise":"Premise","phases":[],"unresolved_threads":[]}'
            )
        if "Return JSON" in last:
            return DummyChunk(
                '{"outline":[{"beat":1,"title":"Intro","purpose":"Start"}],"scene":"Scene txt","embellishment_note":"None"}'
            )
        return DummyChunk("Answer about lore.")

    def stream(self, messages):
        text = "STREAMED ANSWER"
        for ch in text.split():
            yield DummyChunk(ch + " ")


@pytest.fixture(autouse=True)
def patch_llm(monkeypatch):
    from src.agents.langchain.chains import direct_answer, narrative, quest_planner

    monkeypatch.setattr(direct_answer, "ChatOpenAI", lambda *a, **k: DummyLLM())
    monkeypatch.setattr(quest_planner, "ChatOpenAI", lambda *a, **k: DummyLLM())
    monkeypatch.setattr(narrative, "ChatOpenAI", lambda *a, **k: DummyLLM())
    yield


def test_langchain_lore_query_stream(client):
    # initiate conversation with engine=langchain
    r = client.post(
        "/api/v1/chat/message", json={"message": "Tell me about dragons", "engine": "langchain"}
    )
    assert r.status_code == 200
    stream_url = r.json()["stream_url"]
    # consume stream
    s = client.get(stream_url, stream=True)
    events = []
    for line in s.iter_lines():
        if line.startswith(b"data: "):
            payload = json.loads(line[6:])
            events.append(payload)
            if payload.get("type") == "final":
                break
    routes = [e for e in events if e.get("type") == "route"]
    assert routes
    final = next(e for e in events if e.get("type") == "final")
    assert "answer" in final


def test_langchain_quest_plan(client):
    r = client.post(
        "/api/v1/chat/message",
        json={"message": "Generate quest arc about the ancient vault", "engine": "langchain"},
    )
    assert r.status_code == 200
    stream_url = r.json()["stream_url"]
    s = client.get(stream_url)
    # Non-streaming route returns single final event
    assert s.status_code == 200


def test_langchain_trace_flag(client):
    r = client.post(
        "/api/v1/chat/message", json={"message": "Tell me about plains", "engine": "langchain"}
    )
    stream_url = r.json()["stream_url"]
    s = client.get(stream_url + "?trace=1", stream=True)
    saw_trace = False
    for line in s.iter_lines():
        if line.startswith(b"data: "):
            payload = json.loads(line[6:])
            if payload.get("type") == "trace":
                saw_trace = True
                break
    assert saw_trace
