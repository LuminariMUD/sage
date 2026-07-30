"""
Conversation storage service for Luminari Lore Chat Agent.

Manages conversation history, message storage, and SSE stream tracking
using PostgreSQL for persistence and context management.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from ..db import get_postgres_db

logger = logging.getLogger(__name__)


class ConversationMessage:
    """Represents a single message in a conversation."""

    def __init__(
        self,
        id: str,
        conversation_id: str,
        message_type: str,  # 'user' or 'assistant'
        content: str,
        tools_used: list[dict[str, Any]] | None = None,
        sources: list[dict[str, Any]] | None = None,
        entities_discovered: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
        sequence_number: int | None = None,
    ):
        self.id = id
        self.conversation_id = conversation_id
        self.message_type = message_type
        self.content = content
        self.tools_used = tools_used or []
        self.sources = sources or []
        self.entities_discovered = entities_discovered or []
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now()
        self.sequence_number = sequence_number

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for API responses."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "message_type": self.message_type,
            "content": self.content,
            "tools_used": self.tools_used,
            "sources": self.sources,
            "entities_discovered": self.entities_discovered,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sequence_number": self.sequence_number,
        }


class Conversation:
    """Represents a conversation with metadata."""

    def __init__(
        self,
        id: str,
        user_id: str | None = None,
        title: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        message_count: int = 0,
        is_active: bool = True,
    ):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.metadata = metadata or {}
        self.message_count = message_count
        self.is_active = is_active

    def to_dict(self) -> dict[str, Any]:
        """Convert conversation to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
            "message_count": self.message_count,
            "is_active": self.is_active,
        }


class ConversationStorageService:
    """Service for managing conversation storage and retrieval."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def create_conversation(
        self,
        user_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        """Create a new conversation."""
        conversation_id = str(uuid.uuid4())

        postgres_db = await get_postgres_db()

        query = """
        INSERT INTO conversations (id, user_id, title, metadata, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """

        now = datetime.now()
        values = (conversation_id, user_id, title, json.dumps(metadata or {}), now, now)

        try:
            row = await postgres_db.fetchrow(query, *values)
            return self._row_to_conversation(row)
        except Exception as e:
            self.logger.error("Failed to create conversation (%s)", type(e).__name__)
            raise

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID."""
        postgres_db = await get_postgres_db()

        query = "SELECT * FROM conversations WHERE id = $1"

        try:
            row = await postgres_db.fetchrow(query, conversation_id)
            return self._row_to_conversation(row) if row else None
        except Exception as e:
            self.logger.error("Failed to get conversation (%s)", type(e).__name__)
            raise

    async def list_conversations(
        self,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        active_only: bool = True,
    ) -> list[Conversation]:
        """List conversations with pagination."""
        postgres_db = await get_postgres_db()

        conditions = []
        params = []
        param_count = 0

        if user_id:
            param_count += 1
            conditions.append(f"user_id = ${param_count}")
            params.append(user_id)

        if active_only:
            param_count += 1
            conditions.append(f"is_active = ${param_count}")
            params.append(True)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        param_count += 1
        limit_param = f"${param_count}"
        params.append(limit)

        param_count += 1
        offset_param = f"${param_count}"
        params.append(offset)

        query = f"""
        SELECT * FROM conversations
        {where_clause}
        ORDER BY updated_at DESC
        LIMIT {limit_param} OFFSET {offset_param}
        """

        try:
            rows = await postgres_db.fetch(query, *params)
            return [self._row_to_conversation(row) for row in rows]
        except Exception as e:
            self.logger.error("Failed to list conversations (%s)", type(e).__name__)
            raise

    async def add_message(
        self,
        conversation_id: str,
        message_type: str,
        content: str,
        tools_used: list[dict[str, Any]] | None = None,
        sources: list[dict[str, Any]] | None = None,
        entities_discovered: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        """Add a message to a conversation."""
        message_id = str(uuid.uuid4())

        postgres_db = await get_postgres_db()

        query = """
        INSERT INTO conversation_messages
        (id, conversation_id, message_type, content, tools_used, sources, entities_discovered, metadata, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """

        values = (
            message_id,
            conversation_id,
            message_type,
            content,
            json.dumps(tools_used or []),
            json.dumps(sources or []),
            json.dumps(entities_discovered or []),
            json.dumps(metadata or {}),
            datetime.now(),
        )

        try:
            row = await postgres_db.fetchrow(query, *values)
            return self._row_to_message(row)
        except Exception as e:
            self.logger.error("Failed to add message to conversation (%s)", type(e).__name__)
            raise

    async def update_message(
        self,
        message_id: str,
        content: str | None = None,
        tools_used: list[dict[str, Any]] | None = None,
        sources: list[dict[str, Any]] | None = None,
        entities_discovered: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update (overwrite) fields on an existing message. Returns True if updated.

        We avoid per-token DB appends; caller should batch tokens and send full content snapshot.
        """
        postgres_db = await get_postgres_db()

        # Build dynamic update set
        sets = []
        values: list[Any] = []
        idx = 1
        if content is not None:
            sets.append(f"content = ${idx}")
            values.append(content)
            idx += 1
        if tools_used is not None:
            sets.append(f"tools_used = ${idx}")
            values.append(json.dumps(tools_used))
            idx += 1
        if sources is not None:
            sets.append(f"sources = ${idx}")
            values.append(json.dumps(sources))
            idx += 1
        if entities_discovered is not None:
            sets.append(f"entities_discovered = ${idx}")
            values.append(json.dumps(entities_discovered))
            idx += 1
        if metadata is not None:
            sets.append(f"metadata = ${idx}")
            values.append(json.dumps(metadata))
            idx += 1

        if not sets:
            return False

        values.append(message_id)
        query = f"UPDATE conversation_messages SET {', '.join(sets)} WHERE id = ${idx}"
        try:
            result = await postgres_db.execute(query, *values)
            # result format: 'UPDATE <n>'
            return result.split()[0].upper() == "UPDATE" and result.split()[-1] == "1"
        except Exception as e:
            self.logger.error("Failed to update message (%s)", type(e).__name__)
            return False

    async def get_conversation_messages(
        self, conversation_id: str, limit: int = 100, offset: int = 0
    ) -> list[ConversationMessage]:
        """Get messages for a conversation."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT * FROM conversation_messages
        WHERE conversation_id = $1
        ORDER BY sequence_number ASC
        LIMIT $2 OFFSET $3
        """

        try:
            rows = await postgres_db.fetch(query, conversation_id, limit, offset)
            return [self._row_to_message(row) for row in rows]
        except Exception as e:
            self.logger.error("Failed to get messages for conversation (%s)", type(e).__name__)
            raise

    async def get_conversation_context(
        self, conversation_id: str, max_messages: int = 20
    ) -> tuple[Conversation, list[ConversationMessage]]:
        """Get conversation and recent messages for context.

        Returns the most recent messages, ordered from oldest to newest.
        """
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Get the most recent messages (ordered newest first)
        postgres_db = await get_postgres_db()
        query = """
        SELECT * FROM (
            SELECT * FROM conversation_messages
            WHERE conversation_id = $1
            ORDER BY sequence_number DESC
            LIMIT $2
        ) AS recent_messages
        ORDER BY sequence_number ASC
        """

        try:
            rows = await postgres_db.fetch(query, conversation_id, max_messages)
            messages = [self._row_to_message(row) for row in rows]
        except Exception as e:
            self.logger.error("Failed to get conversation context (%s)", type(e).__name__)
            raise

        return conversation, messages

    async def create_stream_session(
        self,
        conversation_id: str,
        current_message_id: str | None = None,
        expires_in_minutes: int = 60,
    ) -> str:
        """Create a new SSE stream session."""
        stream_id = str(uuid.uuid4())

        postgres_db = await get_postgres_db()

        query = """
        INSERT INTO conversation_streams
        (id, conversation_id, stream_id, current_message_id, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING stream_id
        """

        expires_at = datetime.now() + timedelta(minutes=expires_in_minutes)

        try:
            result = await postgres_db.fetchrow(
                query, str(uuid.uuid4()), conversation_id, stream_id, current_message_id, expires_at
            )
            return result["stream_id"]
        except Exception as e:
            self.logger.error("Failed to create stream session (%s)", type(e).__name__)
            raise

    async def get_stream_session(self, stream_id: str) -> dict[str, Any] | None:
        """Get stream session information."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT * FROM conversation_streams
        WHERE stream_id = $1 AND expires_at > CURRENT_TIMESTAMP
        """

        try:
            row = await postgres_db.fetchrow(query, stream_id)
            if not row:
                return None

            return {
                "stream_id": row["stream_id"],
                "conversation_id": row["conversation_id"],
                "status": row["status"],
                "current_message_id": row["current_message_id"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
        except Exception as e:
            self.logger.error("Failed to get stream session (%s)", type(e).__name__)
            raise

    async def update_stream_status(
        self, stream_id: str, status: str, current_message_id: str | None = None
    ):
        """Update stream session status."""
        postgres_db = await get_postgres_db()

        query = """
        UPDATE conversation_streams
        SET status = $1, current_message_id = COALESCE($2, current_message_id)
        WHERE stream_id = $3
        """

        try:
            await postgres_db.execute(query, status, current_message_id, stream_id)
        except Exception as e:
            self.logger.error("Failed to update stream status (%s)", type(e).__name__)
            raise

    async def cleanup_expired_streams(self) -> int:
        """Clean up expired stream sessions."""
        postgres_db = await get_postgres_db()

        try:
            result = await postgres_db.execute(
                "DELETE FROM conversation_streams WHERE expires_at < CURRENT_TIMESTAMP"
            )
            return int(result.split()[-1])  # Extract row count from result
        except Exception as e:
            self.logger.error("Failed to cleanup expired streams (%s)", type(e).__name__)
            return 0

    async def delete_conversation(self, conversation_id: str):
        """Delete a conversation and all its messages."""
        postgres_db = await get_postgres_db()

        query = "DELETE FROM conversations WHERE id = $1"

        try:
            await postgres_db.execute(query, conversation_id)
        except Exception as e:
            self.logger.error("Failed to delete conversation (%s)", type(e).__name__)
            raise

    def _row_to_conversation(self, row) -> Conversation:
        """Convert database row to Conversation object."""
        if not row:
            return None

        return Conversation(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            message_count=row["message_count"],
            is_active=row["is_active"],
        )

    def _row_to_message(self, row) -> ConversationMessage:
        """Convert database row to ConversationMessage object."""
        if not row:
            return None

        # asyncpg Record may not support .get reliably in all contexts; guard access
        seq = None
        try:
            if "sequence_number" in row.keys():  # type: ignore[attr-defined]
                seq = row["sequence_number"]
        except Exception:
            # Fallback silent; sequence number optional
            pass
        return ConversationMessage(
            id=row["id"],
            conversation_id=row["conversation_id"],
            message_type=row["message_type"],
            content=row["content"],
            tools_used=json.loads(row["tools_used"]) if row["tools_used"] else [],
            sources=json.loads(row["sources"]) if row["sources"] else [],
            entities_discovered=(
                json.loads(row["entities_discovered"]) if row["entities_discovered"] else []
            ),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            sequence_number=seq,
        )
