"""Graphiti schema initialization regression tests."""

from __future__ import annotations

import importlib

import pytest

graphiti_module = importlib.import_module("src.graphiti")


class FakeSession:
    def __init__(self, queries: list[str]):
        self.queries = queries

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def run(self, query: str):
        self.queries.append(query)


class FakeDriver:
    def __init__(self):
        self.queries: list[str] = []

    def session(self):
        return FakeSession(self.queries)


class FakeGraphiti:
    def __init__(self, **_kwargs):
        self.driver = FakeDriver()


@pytest.mark.asyncio
async def test_entity_stable_id_constraint_owns_its_index(monkeypatch):
    monkeypatch.setattr(graphiti_module, "LuminariGraphiti", FakeGraphiti)

    graphiti = await graphiti_module.initialize_graphiti()

    constraint = (
        "CREATE CONSTRAINT entity_stable_id_unique IF NOT EXISTS "
        "FOR (n:Entity) REQUIRE n.stable_id IS UNIQUE"
    )
    assert constraint in graphiti.driver.queries
    assert not any(
        query.startswith("CREATE INDEX entity_stable_id ") for query in graphiti.driver.queries
    )
