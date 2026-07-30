"""Regression tests for credential and persistence hardening."""

import os
import stat
from datetime import datetime, timedelta

import pytest

from src.agents.langchain.state_manager import StateManager
from src.auth.api_key import KeyType, MultiKeyAuth
from src.db.neo4j_db import Neo4jDB
from src.db.postgres import PostgresDB


def test_auth_stores_only_key_fingerprints(monkeypatch):
    credential = "test-unit-credential-value"
    monkeypatch.setenv("SAGE_API_KEY", credential)

    auth = MultiKeyAuth()

    assert auth.is_valid_key(credential, KeyType.BACKEND_API)
    assert credential not in repr(auth.keys)
    assert credential.encode() not in auth.keys[KeyType.BACKEND_API]


def test_database_credentials_are_not_retained(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "unit-test-user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "unit-test-password")
    monkeypatch.setenv("POSTGRES_DB", "unit-test-database")
    monkeypatch.setenv("NEO4J_USER", "unit-test-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "unit-test-password")

    postgres = PostgresDB()
    neo4j = Neo4jDB()

    assert not hasattr(postgres, "password")
    assert not hasattr(postgres, "dsn")
    assert not hasattr(neo4j, "password")


def test_pydantic_ai_model_does_not_mutate_environment(monkeypatch):
    pytest.importorskip("pydantic_ai")
    from src.llm.pydantic_ai_factory import create_openai_chat_model

    credential = "test-unit-credential-marker"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    model = create_openai_chat_model(credential)

    assert "OPENAI_API_KEY" not in os.environ
    assert credential not in repr(model)


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("events; DROP TABLE events", "table name"),
        ("embedding) RETURNING *", "column name"),
        ("Entity`) MATCH (n) DETACH DELETE n //", "node label"),
    ],
)
def test_dynamic_database_identifiers_reject_injection(value, kind):
    validator = (
        PostgresDB._validate_identifier if kind != "node label" else Neo4jDB._validate_identifier
    )

    with pytest.raises(ValueError, match="Invalid"):
        validator(value, kind)


@pytest.mark.asyncio
async def test_relationship_mutations_validate_dynamic_identifiers(monkeypatch):
    monkeypatch.setenv("NEO4J_USER", "unit-test-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "unit-test-password")
    neo4j = Neo4jDB()

    with pytest.raises(ValueError, match="Invalid property name"):
        await neo4j.update_relationship_property(
            "relationship-id",
            "value = 1 REMOVE r.secret",
            "value",
        )

    with pytest.raises(ValueError, match="Invalid relationship type"):
        await neo4j.restore_relationship(
            "source-id",
            "target-id",
            "REL] DELETE r //",
            {},
        )


@pytest.mark.asyncio
async def test_state_identifiers_cannot_escape_storage_directory(tmp_path):
    storage_path = tmp_path / "state"
    manager = StateManager(storage_path=storage_path)
    thread_id = "../../outside"

    state = await manager.create_state(thread_id)
    await manager.save_checkpoint(state, "../checkpoint")

    state_files = list(storage_path.glob("*.json"))
    checkpoint_files = list((storage_path / "checkpoints").glob("*.json"))

    assert len(state_files) == 1
    assert len(checkpoint_files) == 1
    assert state_files[0].parent == storage_path
    assert checkpoint_files[0].parent == storage_path / "checkpoints"
    assert stat.S_IMODE(storage_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE((storage_path / "checkpoints").stat().st_mode) == 0o700
    assert stat.S_IMODE(checkpoint_files[0].stat().st_mode) == 0o600
    assert not (tmp_path / "outside.json").exists()

    await manager.delete_state(thread_id)
    assert not state_files[0].exists()


@pytest.mark.asyncio
async def test_expired_hashed_state_is_removed(tmp_path):
    manager = StateManager(storage_path=tmp_path / "state", ttl_hours=1)
    state = await manager.create_state("expired-thread")
    state_file = manager._state_file(state.thread_id)
    expired_time = (datetime.now() - timedelta(hours=2)).timestamp()
    os.utime(state_file, (expired_time, expired_time))

    removed = await manager.cleanup_expired()

    assert removed == 1
    assert not state_file.exists()
    assert "expired-thread" not in manager.cache
