"""Transactional PostgreSQL coverage for embedding profile migration and activation."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from src.db.embedding_profiles import (
    ADOPT_EXISTING_CONFIRMATION,
    EPISODE_EMBEDDING_SPACE,
    EmbeddingSpaceError,
    activate_embedding_space,
    embedding_profile_record,
    preflight_embedding_space,
)
from src.llm.provider_config import resolve_provider_settings

pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "migrations"
    / "0004_embedding_index_profiles.sql"
)
BASELINE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "postgresql_schema.sql"


def _profile(*, dimensions: int = 768):
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OLLAMA_EMBEDDING_DIMENSIONS": str(dimensions),
        }
    ).embedding_profile


class ConnectionPostgres:
    """PostgresDB-compatible wrapper pinned to one transactional connection."""

    def __init__(self, connection):
        self.connection = connection

    async def fetchrow(self, query, *args):
        return await self.connection.fetchrow(query, *args)

    async def fetch(self, query, *args):
        return await self.connection.fetch(query, *args)

    async def fetchval(self, query, *args):
        return await self.connection.fetchval(query, *args)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def _expect_database_rejection(connection, statement: str, *args) -> None:
    savepoint = connection.transaction()
    await savepoint.start()
    try:
        with pytest.raises(asyncpg.PostgresError):
            await connection.execute(statement, *args)
    finally:
        await savepoint.rollback()


@pytest.mark.asyncio
async def test_embedding_migration_preflight_activation_and_profile_immutability():
    schema_name = f"embedding_profile_test_{uuid4().hex}"
    connection = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
    )
    outer = connection.transaction()
    await outer.start()
    try:
        await connection.execute(f'CREATE SCHEMA "{schema_name}"')
        await connection.execute(f'SET LOCAL search_path TO "{schema_name}", public')
        await connection.execute("""
            CREATE TABLE episodes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                embedding vector(768)
            );
            CREATE TABLE chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                embedding vector(384)
            );
            CREATE TABLE search_queries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                query_embedding vector(384)
            );
            CREATE INDEX idx_chunks_embedding ON chunks
                USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            CREATE INDEX idx_search_embedding ON search_queries
                USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 50);
            INSERT INTO episodes (embedding)
            VALUES (array_fill(0.0::real, ARRAY[768])::vector);
            """)
        await connection.execute(MIGRATION_PATH.read_text(encoding="ascii"))

        postgres = ConnectionPostgres(connection)
        profile = _profile()
        before = await preflight_embedding_space(
            postgres,
            EPISODE_EMBEDDING_SPACE,
            configured_profile=profile,
        )
        before_codes = {finding["code"] for finding in before["findings"]}

        assert before["status"] == "blocked"
        assert before["physical"]["dimensions"] == 768
        assert before["physical"]["embedded_rows"] == 1
        assert before["physical"]["index"]["method"] == "hnsw"
        assert "active_space_missing" in before_codes
        assert "stored_profile_missing" in before_codes

        with pytest.raises(EmbeddingSpaceError, match="confirmation"):
            await activate_embedding_space(
                postgres,
                profile,
                adopt_existing=True,
                confirmation="wrong",
            )

        incompatible = embedding_profile_record(_profile(dimensions=1024))
        await connection.execute(
            """
            INSERT INTO embedding_profiles (
                fingerprint, provider, endpoint_class, implementation, model,
                model_revision, dimensions, output_encoding, storage_type,
                normalize, distance_metric, input_type
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            *incompatible.values(),
        )
        await _expect_database_rejection(
            connection,
            """
            UPDATE embedding_index_states
            SET state = 'active',
                profile_fingerprint = $1,
                activated_at = clock_timestamp()
            WHERE semantic_index = 'episodes'
            """,
            incompatible["fingerprint"],
        )

        activated = await activate_embedding_space(
            postgres,
            profile,
            adopt_existing=True,
            confirmation=ADOPT_EXISTING_CONFIRMATION,
        )

        assert activated["status"] == "ready"
        assert activated["metadata"]["profile_fingerprint"] == profile.fingerprint
        assert not [finding for finding in activated["findings"] if finding["severity"] == "error"]

        await _expect_database_rejection(
            connection,
            "UPDATE embedding_profiles SET model = 'changed' WHERE fingerprint = $1",
            profile.fingerprint,
        )

        mismatch = await preflight_embedding_space(
            postgres,
            EPISODE_EMBEDDING_SPACE,
            configured_profile=_profile(dimensions=1024),
        )
        mismatch_codes = {finding["code"] for finding in mismatch["findings"]}
        assert mismatch["status"] == "blocked"
        assert "configured_dimension_mismatch" in mismatch_codes
        assert "profile_fingerprint_mismatch" in mismatch_codes

        legacy_states = await connection.fetch("""
            SELECT semantic_index, state
            FROM embedding_index_states
            WHERE semantic_index LIKE 'legacy_%'
            ORDER BY semantic_index
            """)
        assert [dict(row) for row in legacy_states] == [
            {"semantic_index": "legacy_chunks", "state": "retired"},
            {"semantic_index": "legacy_search_queries", "state": "retired"},
        ]
    finally:
        await outer.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_baseline_schema_declares_supported_episode_space():
    schema_name = f"embedding_baseline_test_{uuid4().hex}"
    connection = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
    )
    outer = connection.transaction()
    await outer.start()
    try:
        await connection.execute(f'CREATE SCHEMA "{schema_name}"')
        await connection.execute(f'SET LOCAL search_path TO "{schema_name}", public')
        baseline_sql = BASELINE_SCHEMA_PATH.read_text(encoding="utf-8")
        # Roles are cluster-global and already exist in the development database;
        # omit only those permission statements from this rollback-only schema test.
        baseline_sql = "\n".join(
            line
            for line in baseline_sql.splitlines()
            if "luminari_reader" not in line and "luminari_writer" not in line
        )
        await connection.execute(baseline_sql)

        postgres = ConnectionPostgres(connection)
        report = await preflight_embedding_space(
            postgres,
            EPISODE_EMBEDDING_SPACE,
            configured_profile=_profile(),
        )

        assert report["physical"]["formatted_type"] == "vector(768)"
        assert report["physical"]["index"]["method"] == "hnsw"
        assert report["metadata"]["state"] == "unverified"
        assert {finding["code"] for finding in report["findings"]} == {
            "active_space_missing",
            "stored_profile_missing",
        }
    finally:
        await outer.rollback()
        await connection.close()
