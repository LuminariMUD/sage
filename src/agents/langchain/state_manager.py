"""State management for persistent ReAct agent context.

This module handles conversation state persistence, scratchpad serialization,
and intelligent context window management.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """Represents the state of a conversation."""

    thread_id: str
    created_at: datetime
    updated_at: datetime
    scratchpad: list[dict[str, Any]]
    context_blocks: list[str]
    generation_history: list[dict[str, Any]]
    metadata: dict[str, Any]
    message_count: int = 0
    total_tokens: int = 0


class StateManager:
    """Manages persistent state for ReAct conversations."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
        max_context_blocks: int = 50,
        max_scratchpad_size: int = 100,
        max_generation_history: int = 20,
        ttl_hours: int = 24,
    ):
        """Initialize the state manager.

        Args:
            storage_path: Path to store state files
            max_context_blocks: Maximum context blocks to retain
            max_scratchpad_size: Maximum scratchpad entries
            max_generation_history: Maximum generation history items
            ttl_hours: Time to live for inactive states
        """
        if storage_path is None:
            state_home = Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
            storage_path = state_home / "luminari_sage" / "react_state"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.storage_path.chmod(0o700)

        self.max_context_blocks = max_context_blocks
        self.max_scratchpad_size = max_scratchpad_size
        self.max_generation_history = max_generation_history
        self.ttl_hours = ttl_hours

        # In-memory cache for active states
        self.cache: dict[str, ConversationState] = {}

        # Track access times for LRU eviction
        self.access_times: dict[str, datetime] = {}

    @staticmethod
    def _storage_key(*parts: str) -> str:
        """Map external identifiers to a fixed, traversal-safe filename."""
        payload = "\0".join(parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _secure_opener(path: str, flags: int) -> int:
        """Create state files as owner-readable/writable only."""
        return os.open(path, flags, 0o600)

    def _state_file(self, thread_id: str) -> Path:
        return self.storage_path / f"{self._storage_key(thread_id)}.json"

    def _checkpoint_file(self, thread_id: str, checkpoint_id: str) -> Path:
        return (
            self.storage_path
            / "checkpoints"
            / f"{self._storage_key(thread_id, checkpoint_id)}.json"
        )

    async def get_state(self, thread_id: str) -> ConversationState | None:
        """Get conversation state by thread ID.

        Args:
            thread_id: Unique thread identifier

        Returns:
            ConversationState if exists, None otherwise
        """
        # Check cache first
        if thread_id in self.cache:
            self.access_times[thread_id] = datetime.now()
            return self.cache[thread_id]

        # Try to load from disk
        state_file = self._state_file(thread_id)
        if state_file.exists():
            try:
                async with aiofiles.open(state_file) as f:
                    data = json.loads(await f.read())

                # Reconstruct state
                state = ConversationState(
                    thread_id=data["thread_id"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    scratchpad=data["scratchpad"],
                    context_blocks=data["context_blocks"],
                    generation_history=data["generation_history"],
                    metadata=data["metadata"],
                    message_count=data.get("message_count", 0),
                    total_tokens=data.get("total_tokens", 0),
                )

                # Check TTL
                if datetime.now() - state.updated_at > timedelta(hours=self.ttl_hours):
                    logger.info("Expired state removed")
                    await self.delete_state(thread_id)
                    return None

                # Add to cache
                self.cache[thread_id] = state
                self.access_times[thread_id] = datetime.now()

                return state

            except Exception as e:
                logger.error("Failed to load state (%s)", type(e).__name__)
                return None

        return None

    async def save_state(self, state: ConversationState) -> None:
        """Save conversation state.

        Args:
            state: ConversationState to save
        """
        # Update timestamp
        state.updated_at = datetime.now()

        # Apply size limits
        state = self._apply_limits(state)

        # Update cache
        self.cache[state.thread_id] = state
        self.access_times[state.thread_id] = datetime.now()

        # Serialize to JSON
        data = {
            "thread_id": state.thread_id,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "scratchpad": state.scratchpad,
            "context_blocks": state.context_blocks,
            "generation_history": state.generation_history,
            "metadata": state.metadata,
            "message_count": state.message_count,
            "total_tokens": state.total_tokens,
        }

        # Save to disk
        state_file = self._state_file(state.thread_id)
        try:
            async with aiofiles.open(state_file, "w", opener=self._secure_opener) as f:
                await f.write(json.dumps(data, indent=2))
            state_file.chmod(0o600)

            logger.debug("Saved state")

        except Exception as e:
            logger.error("Failed to save state (%s)", type(e).__name__)

    async def create_state(
        self, thread_id: str, metadata: dict[str, Any] | None = None
    ) -> ConversationState:
        """Create a new conversation state.

        Args:
            thread_id: Unique thread identifier
            metadata: Optional metadata

        Returns:
            New ConversationState
        """
        state = ConversationState(
            thread_id=thread_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            scratchpad=[],
            context_blocks=[],
            generation_history=[],
            metadata=metadata or {},
        )

        await self.save_state(state)
        return state

    async def update_state(
        self,
        thread_id: str,
        scratchpad_entry: dict[str, Any] | None = None,
        context_blocks: list[str] | None = None,
        generation: dict[str, Any] | None = None,
        metadata_update: dict[str, Any] | None = None,
    ) -> ConversationState:
        """Update an existing state or create if doesn't exist.

        Args:
            thread_id: Thread identifier
            scratchpad_entry: New scratchpad entry to add
            context_blocks: New context blocks to add
            generation: New generation to add
            metadata_update: Metadata to update

        Returns:
            Updated ConversationState
        """
        # Get or create state
        state = await self.get_state(thread_id)
        if not state:
            state = await self.create_state(thread_id)

        # Update components
        if scratchpad_entry:
            state.scratchpad.append(scratchpad_entry)

        if context_blocks:
            state.context_blocks.extend(context_blocks)

        if generation:
            state.generation_history.append(generation)

        if metadata_update:
            state.metadata.update(metadata_update)

        # Increment message count
        state.message_count += 1

        # Save updated state
        await self.save_state(state)
        return state

    async def delete_state(self, thread_id: str) -> None:
        """Delete a conversation state.

        Args:
            thread_id: Thread identifier
        """
        # Remove from cache
        if thread_id in self.cache:
            del self.cache[thread_id]
        if thread_id in self.access_times:
            del self.access_times[thread_id]

        # Remove from disk
        state_file = self._state_file(thread_id)
        if state_file.exists():
            state_file.unlink()
            logger.info("Deleted state")

    async def cleanup_expired(self) -> int:
        """Clean up expired states.

        Returns:
            Number of states cleaned up
        """
        count = 0
        now = datetime.now()
        cutoff = now - timedelta(hours=self.ttl_hours)

        # Check all state files
        for state_file in self.storage_path.glob("*.json"):
            try:
                # Check modification time
                mtime = datetime.fromtimestamp(state_file.stat().st_mtime)
                if mtime < cutoff:
                    # Hashed filenames deliberately do not reveal the thread ID.
                    # Read the stored identifier only to evict the matching cache
                    # entry, then unlink the file we already resolved.
                    thread_id = None
                    try:
                        async with aiofiles.open(state_file) as f:
                            data = json.loads(await f.read())
                        thread_id = data.get("thread_id")
                    except (OSError, json.JSONDecodeError):
                        pass

                    state_file.unlink(missing_ok=True)
                    if isinstance(thread_id, str):
                        self.cache.pop(thread_id, None)
                        self.access_times.pop(thread_id, None)
                    count += 1

            except Exception as e:
                logger.error("Error checking state file (%s)", type(e).__name__)

        logger.info(f"Cleaned up {count} expired states")
        return count

    def _apply_limits(self, state: ConversationState) -> ConversationState:
        """Apply size limits to state components.

        Args:
            state: State to limit

        Returns:
            Limited state
        """
        # Limit scratchpad size (keep most recent)
        if len(state.scratchpad) > self.max_scratchpad_size:
            # Keep first few (for context) and most recent
            keep_start = 5
            keep_recent = self.max_scratchpad_size - keep_start
            state.scratchpad = state.scratchpad[:keep_start] + state.scratchpad[-keep_recent:]

            # Add truncation marker
            state.scratchpad.insert(
                keep_start,
                {
                    "step": "truncated",
                    "note": f"Removed {len(state.scratchpad) - self.max_scratchpad_size} entries",
                },
            )

        # Limit context blocks (keep most relevant)
        if len(state.context_blocks) > self.max_context_blocks:
            # Simple truncation for now - could be enhanced with relevance scoring
            state.context_blocks = state.context_blocks[-self.max_context_blocks :]

        # Limit generation history (keep most recent)
        if len(state.generation_history) > self.max_generation_history:
            state.generation_history = state.generation_history[-self.max_generation_history :]

        return state

    async def get_checkpoint(self, thread_id: str, checkpoint_id: str) -> ConversationState | None:
        """Get a checkpoint of the state.

        Args:
            thread_id: Thread identifier
            checkpoint_id: Checkpoint identifier

        Returns:
            Checkpointed state if exists
        """
        checkpoint_file = self._checkpoint_file(thread_id, checkpoint_id)
        if checkpoint_file.exists():
            try:
                async with aiofiles.open(checkpoint_file) as f:
                    data = json.loads(await f.read())

                return ConversationState(
                    thread_id=data["thread_id"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    scratchpad=data["scratchpad"],
                    context_blocks=data["context_blocks"],
                    generation_history=data["generation_history"],
                    metadata=data["metadata"],
                    message_count=data.get("message_count", 0),
                    total_tokens=data.get("total_tokens", 0),
                )
            except Exception as e:
                logger.error("Failed to load checkpoint (%s)", type(e).__name__)

        return None

    async def save_checkpoint(self, state: ConversationState, checkpoint_id: str) -> None:
        """Save a checkpoint of the current state.

        Args:
            state: State to checkpoint
            checkpoint_id: Checkpoint identifier
        """
        checkpoint_dir = self.storage_path / "checkpoints"
        checkpoint_dir.mkdir(mode=0o700, exist_ok=True)
        checkpoint_dir.chmod(0o700)

        checkpoint_file = self._checkpoint_file(state.thread_id, checkpoint_id)

        data = {
            "thread_id": state.thread_id,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "scratchpad": state.scratchpad,
            "context_blocks": state.context_blocks,
            "generation_history": state.generation_history,
            "metadata": state.metadata,
            "message_count": state.message_count,
            "total_tokens": state.total_tokens,
            "checkpoint_id": checkpoint_id,
            "checkpoint_time": datetime.now().isoformat(),
        }

        try:
            async with aiofiles.open(checkpoint_file, "w", opener=self._secure_opener) as f:
                await f.write(json.dumps(data, indent=2))
            checkpoint_file.chmod(0o600)

            logger.info("Saved checkpoint")

        except Exception as e:
            logger.error("Failed to save checkpoint (%s)", type(e).__name__)

    def get_summary(self, state: ConversationState) -> dict[str, Any]:
        """Get a summary of the conversation state.

        Args:
            state: State to summarize

        Returns:
            Summary dictionary
        """
        return {
            "thread_id": state.thread_id,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "message_count": state.message_count,
            "scratchpad_size": len(state.scratchpad),
            "context_blocks_count": len(state.context_blocks),
            "generations_count": len(state.generation_history),
            "total_tokens": state.total_tokens,
            "metadata": state.metadata,
        }


# Global state manager instance
_state_manager: StateManager | None = None


def get_state_manager() -> StateManager:
    """Get the global state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


async def initialize_state_manager(config: dict[str, Any] | None = None) -> StateManager:
    """Initialize the global state manager with config.

    Args:
        config: Configuration dictionary

    Returns:
        Initialized StateManager
    """
    global _state_manager

    if config:
        _state_manager = StateManager(
            storage_path=config.get("storage_path"),
            max_context_blocks=config.get("max_context_blocks", 50),
            max_scratchpad_size=config.get("max_scratchpad_size", 100),
            max_generation_history=config.get("max_generation_history", 20),
            ttl_hours=config.get("ttl_hours", 24),
        )
    else:
        _state_manager = StateManager()

    # Run initial cleanup
    await _state_manager.cleanup_expired()

    return _state_manager
