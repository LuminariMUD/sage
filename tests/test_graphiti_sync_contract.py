"""Regression tests for cross-store episode sync invariants."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from src.scripts import sync_episodes_to_graphiti as sync


def _episode():
    return {
        "id": uuid4(),
        "text": "A bounded piece of lore.",
        "document_id": uuid4(),
        "episode_index": 3,
    }


def _postgres_for(episode):
    return SimpleNamespace(
        fetch=AsyncMock(side_effect=[[episode], []]),
        execute=AsyncMock(),
    )


def _graphiti():
    return SimpleNamespace(add_episode_with_lore_relationships=AsyncMock())


async def test_incremental_sync_marks_postgres_after_verified_link(monkeypatch):
    episode = _episode()
    postgres = _postgres_for(episode)
    graphiti = _graphiti()
    monkeypatch.setattr(sync, "get_episode_link_state", AsyncMock(return_value={}))
    monkeypatch.setattr(sync, "ensure_episode_link", AsyncMock())
    monkeypatch.setattr(sync.asyncio, "sleep", AsyncMock())

    result = await sync.sync_episodes_incremental(postgres, graphiti, batch_size=1)

    assert result == (1, 0)
    graphiti.add_episode_with_lore_relationships.assert_awaited_once()
    sync.ensure_episode_link.assert_awaited_once_with(graphiti, episode)
    postgres.execute.assert_awaited_once()


async def test_incremental_sync_refuses_unverified_link(monkeypatch):
    episode = _episode()
    postgres = _postgres_for(episode)
    graphiti = _graphiti()
    monkeypatch.setattr(sync, "get_episode_link_state", AsyncMock(return_value={}))
    monkeypatch.setattr(
        sync,
        "ensure_episode_link",
        AsyncMock(side_effect=RuntimeError("missing link")),
    )
    monkeypatch.setattr(sync.asyncio, "sleep", AsyncMock())

    result = await sync.sync_episodes_incremental(postgres, graphiti, batch_size=1)

    assert result == (0, 1)
    postgres.execute.assert_not_awaited()


async def test_incremental_sync_resumes_an_exact_existing_link(monkeypatch):
    episode = _episode()
    postgres = _postgres_for(episode)
    graphiti = _graphiti()
    exact_link = {
        "candidate_count": 1,
        "stable_id_count": 1,
        "source_description_count": 1,
        "exact_count": 1,
    }
    monkeypatch.setattr(
        sync,
        "get_episode_link_state",
        AsyncMock(return_value=exact_link),
    )
    monkeypatch.setattr(sync, "ensure_episode_link", AsyncMock())
    monkeypatch.setattr(sync.asyncio, "sleep", AsyncMock())

    result = await sync.sync_episodes_incremental(postgres, graphiti, batch_size=1)

    assert result == (1, 0)
    graphiti.add_episode_with_lore_relationships.assert_not_awaited()
    sync.ensure_episode_link.assert_not_awaited()
    postgres.execute.assert_awaited_once()
