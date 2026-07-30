"""PostgreSQL database connection manager with pgvector support."""

import os
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from asyncpg import Connection, Pool
from dotenv import load_dotenv

load_dotenv()

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresDB:
    """PostgreSQL database manager with connection pooling."""

    def __init__(self):
        self.pool: Pool | None = None
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.user = self._required_env("POSTGRES_USER")
        self.database = self._required_env("POSTGRES_DB")
        # Validate the password at initialization without retaining a plaintext DSN.
        self._required_env("POSTGRES_PASSWORD")

    @staticmethod
    def _required_env(name: str) -> str:
        """Return a required environment value without including it in errors."""
        value = os.getenv(name)
        if not value:
            raise ValueError(f"{name} environment variable is required")
        return value

    @staticmethod
    def _validate_identifier(value: str, kind: str) -> str:
        """Validate a SQL identifier before it is interpolated into a query."""
        parts = value.split(".")
        if not parts or any(not _SQL_IDENTIFIER.fullmatch(part) for part in parts):
            raise ValueError(f"Invalid {kind}")
        return ".".join(parts)

    async def connect(self) -> None:
        """Create connection pool."""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self._required_env("POSTGRES_PASSWORD"),
                database=self.database,
                min_size=5,
                max_size=20,
                command_timeout=60,
            )

            # Enable pgvector extension
            async with self.pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[Connection, None]:
        """Acquire a connection from the pool."""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results."""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        """Execute a query and fetch all results."""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Execute a query and fetch a single row."""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Execute a query and fetch a single value."""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute_query(
        self, query: str, params: list | tuple | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute a query with a sequence of parameters and return rows as dicts.

        Mirrors the Neo4j wrapper's execute_query so callers can treat both stores
        alike. Parameters are passed as one sequence (not varargs), and rows come
        back as plain dicts rather than asyncpg Records.

        Args:
            query: SQL using positional placeholders ($1, $2, ...)
            params: Sequence of parameter values, or None

        Returns:
            List of rows as dictionaries (empty for statements that return no rows)
        """
        async with self.acquire() as conn:
            records = await conn.fetch(query, *(params or []))
            return [dict(record) for record in records]

    async def init_schema(self, schema_file: str) -> None:
        """Initialize database schema from SQL file."""
        with open(schema_file) as f:
            schema_sql = f.read()

        async with self.acquire() as conn:
            await conn.execute(schema_sql)

    async def vector_search(
        self,
        table: str,
        embedding_column: str,
        query_embedding: list[float],
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list:
        """Perform vector similarity search using pgvector."""
        safe_table = self._validate_identifier(table, "table name")
        safe_embedding_column = self._validate_identifier(embedding_column, "embedding column name")
        # Only identifiers accepted by _validate_identifier are interpolated.
        query = f"""
            SELECT *, 1 - ({safe_embedding_column} <=> $1::vector) as similarity
            FROM {safe_table}
            WHERE 1 - ({safe_embedding_column} <=> $1::vector) > $2
            ORDER BY {safe_embedding_column} <=> $1::vector
            LIMIT $3
        """
        return await self.fetch(query, query_embedding, threshold, limit)


# Global database instance
_postgres_db: PostgresDB | None = None


async def get_postgres_db() -> PostgresDB:
    """Get or create the global PostgreSQL database instance."""
    global _postgres_db
    if _postgres_db is None:
        _postgres_db = PostgresDB()
        await _postgres_db.connect()
    return _postgres_db


async def close_postgres_db() -> None:
    """Close the global PostgreSQL database connection."""
    global _postgres_db
    if _postgres_db:
        await _postgres_db.disconnect()
        _postgres_db = None
