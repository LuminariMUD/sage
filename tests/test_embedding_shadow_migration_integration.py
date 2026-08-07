"""Rollback-only PostgreSQL coverage for isolated embedding shadow generations."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from src.llm.provider_config import resolve_provider_settings
from src.retrieval.shadow_embeddings import (
    ShadowEmbeddingError,
    ShadowEmbeddingRepository,
    shadow_search_query,
)

pytestmark = pytest.mark.integration

MIGRATIONS = tuple(
    Path(__file__).resolve().parents[1] / "schemas" / "migrations" / name
    for name in (
        "0004_embedding_index_profiles.sql",
        "0005_embedding_shadow_spaces.sql",
    )
)
BASELINE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "postgresql_schema.sql"
SOURCE_A = "sha256:v1:" + "a" * 64
SOURCE_B = "sha256:v1:" + "b" * 64
SOURCE_C = "sha256:v1:" + "c" * 64


def _profile(*, dimensions: int = 1024):
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OLLAMA_EMBEDDING_DIMENSIONS": str(dimensions),
            "OLLAMA_EMBEDDING_BATCH_SIZE": "32",
        }
    ).embedding_profile


class ConnectionPostgres:
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
async def test_shadow_backfill_is_profile_isolated_source_fenced_and_indexed():
    schema_name = f"embedding_shadow_test_{uuid4().hex}"
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
            CREATE TABLE lore_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                stable_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE episodes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES lore_documents(id),
                episode_index INTEGER NOT NULL,
                text TEXT NOT NULL,
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
            CREATE TABLE graph_sync_jobs (
                episode_id UUID PRIMARY KEY REFERENCES episodes(id),
                desired_source_fingerprint TEXT NOT NULL
            );
            CREATE INDEX idx_chunks_embedding ON chunks
                USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            CREATE INDEX idx_search_embedding ON search_queries
                USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 50);
            """)
        document_id = await connection.fetchval(
            "INSERT INTO lore_documents (stable_id) VALUES ('doc_alpha') RETURNING id"
        )
        episode_id = await connection.fetchval(
            """
            INSERT INTO episodes (document_id, episode_index, text, embedding)
            VALUES (
                $1, 0, 'Alpha source text',
                array_prepend(1.0::real, array_fill(0.0::real, ARRAY[767]))::vector
            )
            RETURNING id
            """,
            document_id,
        )
        await connection.execute(
            "INSERT INTO graph_sync_jobs (episode_id, desired_source_fingerprint) VALUES ($1, $2)",
            episode_id,
            SOURCE_A,
        )
        for migration in MIGRATIONS:
            await connection.execute(migration.read_text(encoding="ascii"))

        postgres = ConnectionPostgres(connection)
        repository = ShadowEmbeddingRepository(postgres)
        profile = _profile()
        registered = await repository.register(profile)

        assert registered["spaces"][0]["state"] == "registered"
        assert registered["spaces"][0]["coverage"]["current_rows"] == 0
        assert (
            await connection.fetchval(
                "SELECT vector_dims(embedding) FROM episodes WHERE id = $1", episode_id
            )
            == 768
        )

        snapshot = await repository.current_snapshot()
        pending = await repository.pending_episodes(profile, limit=profile.batch_size)
        run_id = await repository.start_run(profile, snapshot, provider_request_limit=1)
        ordinal = await repository.reserve_batch(run_id, profile, pending)
        vector = [1.0, *([0.0] * 1023)]
        with pytest.raises(ShadowEmbeddingError, match="differ from reservation"):
            await repository.finalize_batch_success(
                run_id,
                ordinal,
                profile,
                [replace(pending[0], episode_id=uuid4())],
                [vector],
                latency_ms=1,
                metadata={
                    "input_tokens": 1,
                    "total_tokens": 1,
                    "estimated_cost_usd": None,
                    "actual_model": profile.model,
                },
            )
        stored = await repository.finalize_batch_success(
            run_id,
            ordinal,
            profile,
            pending,
            [vector],
            latency_ms=7,
            metadata={
                "input_tokens": 3,
                "total_tokens": 3,
                "estimated_cost_usd": None,
                "actual_model": profile.model,
            },
        )
        completed = await repository.finish_run(run_id, profile, snapshot)

        assert stored is True
        assert completed["status"] == "completed"
        assert completed["provider_requests"] == {
            "maximum": 1,
            "reserved": 1,
            "succeeded": 1,
        }
        assert (
            await connection.fetchval(
                """
            SELECT vector_dims(embedding)
            FROM episode_embedding_shadows
            WHERE profile_fingerprint = $1 AND episode_id = $2
            """,
                profile.fingerprint,
                episode_id,
            )
            == 1024
        )

        ready = await repository.build_index(profile)
        assert ready["spaces"][0]["ready"] is True
        results = await connection.fetch(
            shadow_search_query(profile),
            "[" + ",".join(map(str, vector)) + "]",
            10,
        )
        assert [(row["document_stable_id"], row["episode_index"]) for row in results] == [
            ("doc_alpha", 0)
        ]
        assert await connection.fetchval("""
            SELECT state FROM embedding_index_states
            WHERE semantic_index = 'episodes' AND physical_space = 'episodes.embedding'
            """) == "unverified"

        index_name = ready["spaces"][0]["index"]["name"]
        await connection.execute(f'DROP INDEX "{index_name}"')
        await connection.execute(f"""
            CREATE INDEX "{index_name}"
            ON episode_embedding_shadows
            USING hnsw ((embedding::vector(1024)) vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE profile_fingerprint = '{profile.fingerprint}' OR true
            """)
        with pytest.raises(ShadowEmbeddingError, match="incompatible"):
            await repository.build_index(profile)

        await _expect_database_rejection(
            connection,
            """
            UPDATE episode_embedding_shadows
            SET dimensions = 3, embedding = '[1,0,0]'::vector
            WHERE profile_fingerprint = $1 AND episode_id = $2
            """,
            profile.fingerprint,
            episode_id,
        )
        await _expect_database_rejection(
            connection,
            """
            UPDATE embedding_shadow_batches
            SET actual_model = 'changed'
            WHERE run_id = $1 AND ordinal = $2
            """,
            run_id,
            ordinal,
        )
        await _expect_database_rejection(
            connection,
            """
            UPDATE embedding_shadow_batch_items
            SET source_fingerprint = $3
            WHERE run_id = $1 AND batch_ordinal = $2
            """,
            run_id,
            ordinal,
            SOURCE_B,
        )

        second_episode_id = await connection.fetchval(
            """
            INSERT INTO episodes (document_id, episode_index, text)
            VALUES ($1, 1, 'Beta source text')
            RETURNING id
            """,
            document_id,
        )
        await connection.execute(
            "INSERT INTO graph_sync_jobs (episode_id, desired_source_fingerprint) VALUES ($1, $2)",
            second_episode_id,
            SOURCE_B,
        )
        changed_snapshot = await repository.current_snapshot()
        changed_pending = await repository.pending_episodes(profile, limit=profile.batch_size)
        changed_run = await repository.start_run(
            profile, changed_snapshot, provider_request_limit=1
        )
        changed_ordinal = await repository.reserve_batch(changed_run, profile, changed_pending)
        await connection.execute(
            "UPDATE graph_sync_jobs SET desired_source_fingerprint = $2 WHERE episode_id = $1",
            second_episode_id,
            SOURCE_C,
        )
        source_fenced = await repository.finalize_batch_success(
            changed_run,
            changed_ordinal,
            profile,
            changed_pending,
            [vector],
            latency_ms=5,
            metadata={
                "input_tokens": 2,
                "total_tokens": 2,
                "estimated_cost_usd": None,
                "actual_model": profile.model,
            },
        )
        stopped = await repository.finish_run(changed_run, profile, changed_snapshot)

        assert source_fenced is False
        assert stopped["status"] == "stopped"
        assert stopped["failure_code"] == "source_snapshot_changed"
        assert (
            await connection.fetchval(
                """
            SELECT count(*) FROM episode_embedding_shadows
            WHERE profile_fingerprint = $1 AND episode_id = $2
            """,
                profile.fingerprint,
                second_episode_id,
            )
            == 0
        )

        recovery_snapshot = await repository.current_snapshot()
        recovery_pending = await repository.pending_episodes(profile, limit=profile.batch_size)
        abandoned_run = await repository.start_run(
            profile, recovery_snapshot, provider_request_limit=1
        )
        abandoned_ordinal = await repository.reserve_batch(abandoned_run, profile, recovery_pending)
        recovered = await repository.recover_run(abandoned_run)

        assert recovered["status"] == "stopped"
        assert recovered["failure_code"] == "operator_recovery"
        assert (
            await connection.fetchval(
                """
                SELECT state FROM embedding_shadow_batches
                WHERE run_id = $1 AND ordinal = $2
                """,
                abandoned_run,
                abandoned_ordinal,
            )
            == "abandoned"
        )

        resumable_run = await repository.start_run(
            profile, recovery_snapshot, provider_request_limit=1
        )
        resumed_recovery = await repository.recover_run(resumable_run)
        assert resumed_recovery["failure_code"] == "operator_recovery"
        inventory = await repository.inventory(profile)
        assert inventory["spaces"][0]["latest_run"]["run_id"] == str(resumable_run)
        assert inventory["spaces"][0]["latest_run"]["status"] == "stopped"
    finally:
        await outer.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_baseline_schema_contains_shadow_storage_without_candidate_rows():
    schema_name = f"embedding_shadow_baseline_test_{uuid4().hex}"
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
        assert MIGRATIONS[1].read_text(encoding="ascii").strip() in baseline_sql
        baseline_sql = "\n".join(
            line
            for line in baseline_sql.splitlines()
            if "luminari_reader" not in line and "luminari_writer" not in line
        )
        await connection.execute(baseline_sql)

        tables = await connection.fetchrow("""
            SELECT
                to_regclass('embedding_shadow_spaces')::text AS spaces,
                to_regclass('embedding_shadow_runs')::text AS runs,
                to_regclass('embedding_shadow_batches')::text AS batches,
                to_regclass('episode_embedding_shadows')::text AS vectors
            """)
        assert all(tables.values())
        assert await connection.fetchval("SELECT count(*) FROM embedding_shadow_spaces") == 0
        assert await connection.fetchval("SELECT count(*) FROM episode_embedding_shadows") == 0
    finally:
        await outer.rollback()
        await connection.close()
