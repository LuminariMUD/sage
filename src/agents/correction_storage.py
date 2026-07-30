"""
Correction storage service for relationship corrections audit trail.

Handles storing complete relationship data before modifications and provides
rollback capabilities by restoring the exact original state including embeddings.
"""

import json
from typing import Any

from ..db import get_neo4j_db, get_postgres_db


class CorrectionStorageService:
    """Service for storing and managing relationship corrections."""

    @staticmethod
    async def store_correction(
        correction_id: str,
        validation_report_id: str | None,
        correction_batch_id: str,
        correction_type: str,
        action: str,
        confidence_score: float,
        agent_reasoning: str,
        relationship_data: dict[str, Any],
        new_properties: dict[str, Any] | None = None,
        original_semantic_type: str | None = None,
        new_semantic_type: str | None = None,
        duplicate_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Store a correction record with complete relationship backup data.

        Args:
            correction_id: Unique ID for this correction
            validation_report_id: ID of the validation report (if any)
            correction_batch_id: ID grouping corrections from same run
            correction_type: 'DEDUPLICATION' or 'SEMANTIC_STANDARDIZATION'
            action: 'DELETE' or 'UPDATE'
            confidence_score: Agent confidence in this correction
            agent_reasoning: Why this correction was made
            relationship_data: Complete Neo4j relationship data for backup
            new_properties: Updated properties (for UPDATE actions)
            original_semantic_type: Original semantic type
            new_semantic_type: New semantic type (for standardization)
            duplicate_count: Number of duplicates found (for deduplication)
            metadata: Additional metadata

        Returns:
            True if stored successfully
        """
        postgres_db = await get_postgres_db()

        # Extract relationship info from backup data
        relationship_id = relationship_data.get("id")
        relationship_type = relationship_data.get("type")
        source_id = relationship_data.get("source_id")
        target_id = relationship_data.get("target_id")
        source_name = relationship_data.get("source_name")
        target_name = relationship_data.get("target_name")
        source_labels = relationship_data.get("source_labels", [])
        target_labels = relationship_data.get("target_labels", [])
        original_properties = relationship_data.get("properties", {})

        query = """
        INSERT INTO relationship_corrections (
            correction_id, validation_report_id, correction_batch_id,
            correction_type, action, confidence_score, agent_reasoning,
            relationship_id, relationship_type, source_node_id, target_node_id,
            source_node_name, target_node_name, source_node_labels, target_node_labels,
            original_properties, new_properties,
            original_semantic_type, new_semantic_type, duplicate_count,
            metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
        )
        """

        try:
            await postgres_db.execute_query(
                query,
                [
                    correction_id,
                    validation_report_id,
                    correction_batch_id,
                    correction_type,
                    action,
                    confidence_score,
                    agent_reasoning,
                    relationship_id,
                    relationship_type,
                    source_id,
                    target_id,
                    source_name,
                    target_name,
                    source_labels,
                    target_labels,
                    json.dumps(original_properties),  # Store as JSON
                    json.dumps(new_properties) if new_properties else None,
                    original_semantic_type,
                    new_semantic_type,
                    duplicate_count,
                    json.dumps(metadata or {}),
                ],
            )
            return True
        except Exception as e:
            print(f"Error storing correction ({type(e).__name__})")
            return False

    @staticmethod
    async def get_correction(correction_id: str) -> dict[str, Any] | None:
        """Get a specific correction record."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT * FROM relationship_corrections
        WHERE correction_id = $1
        """

        result = await postgres_db.execute_query(query, [correction_id])
        return result[0] if result else None

    @staticmethod
    async def get_corrections_for_batch(correction_batch_id: str) -> list[dict[str, Any]]:
        """Get all corrections for a specific batch."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT * FROM relationship_corrections
        WHERE correction_batch_id = $1
        ORDER BY applied_at ASC
        """

        return await postgres_db.execute_query(query, [correction_batch_id])

    @staticmethod
    async def get_corrections_for_report(validation_report_id: str) -> list[dict[str, Any]]:
        """Get all corrections for a validation report."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT * FROM relationship_corrections
        WHERE validation_report_id = $1
        ORDER BY applied_at ASC
        """

        return await postgres_db.execute_query(query, [validation_report_id])

    @staticmethod
    async def rollback_correction(
        correction_id: str, rollback_by: str, rollback_reason: str = ""
    ) -> bool:
        """
        Rollback a single correction by restoring the original relationship.

        Args:
            correction_id: ID of the correction to rollback
            rollback_by: Who is performing the rollback
            rollback_reason: Why the rollback is being performed

        Returns:
            True if rollback was successful
        """
        postgres_db = await get_postgres_db()
        neo4j_db = await get_neo4j_db()

        # Get the correction record
        correction = await CorrectionStorageService.get_correction(correction_id)
        if not correction or correction.get("rolled_back"):
            return False

        try:
            # Restore the relationship based on the action type
            if correction["action"] == "DELETE":
                # Recreate the deleted relationship with all original properties
                original_props = json.loads(correction["original_properties"])
                success = await neo4j_db.restore_relationship(
                    source_id=correction["source_node_id"],
                    target_id=correction["target_node_id"],
                    rel_type=correction["relationship_type"],
                    properties=original_props,
                )
                if not success:
                    return False

            elif correction["action"] == "UPDATE":
                # Restore original properties (especially semantic type)
                original_props = json.loads(correction["original_properties"])
                # For semantic standardization, we need to restore the original 'name' property
                if correction["correction_type"] == "SEMANTIC_STANDARDIZATION":
                    success = await neo4j_db.update_relationship_property(
                        relationship_id=correction["relationship_id"],
                        property_name="name",
                        property_value=correction["original_semantic_type"],
                    )
                    if not success:
                        return False

            # Mark the correction as rolled back
            rollback_query = """
            UPDATE relationship_corrections
            SET rolled_back = TRUE,
                rollback_at = NOW(),
                rollback_by = $1,
                rollback_reason = $2
            WHERE correction_id = $3
            """

            await postgres_db.execute_query(
                rollback_query, [rollback_by, rollback_reason, correction_id]
            )

            return True

        except Exception as e:
            print(f"Error rolling back correction {correction_id} ({type(e).__name__})")
            return False

    @staticmethod
    async def rollback_batch(
        correction_batch_id: str, rollback_by: str, rollback_reason: str = ""
    ) -> dict[str, int]:
        """
        Rollback all corrections in a batch.

        Args:
            correction_batch_id: ID of the batch to rollback
            rollback_by: Who is performing the rollback
            rollback_reason: Why the rollback is being performed

        Returns:
            Dictionary with rollback statistics
        """
        corrections = await CorrectionStorageService.get_corrections_for_batch(correction_batch_id)

        stats = {"total": len(corrections), "successful": 0, "failed": 0, "already_rolled_back": 0}

        # Rollback in reverse order (most recent first) to handle dependencies
        for correction in reversed(corrections):
            if correction.get("rolled_back"):
                stats["already_rolled_back"] += 1
                continue

            success = await CorrectionStorageService.rollback_correction(
                correction["correction_id"], rollback_by, rollback_reason
            )

            if success:
                stats["successful"] += 1
            else:
                stats["failed"] += 1

        return stats

    @staticmethod
    async def get_correction_batch_summary(correction_batch_id: str) -> dict[str, Any] | None:
        """Get summary statistics for a correction batch."""
        postgres_db = await get_postgres_db()

        query = "SELECT * FROM get_correction_batch_summary($1)"
        result = await postgres_db.execute_query(query, [correction_batch_id])

        return result[0] if result else None

    @staticmethod
    async def list_recent_corrections(limit: int = 100) -> list[dict[str, Any]]:
        """List recent corrections for monitoring."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT correction_id, correction_batch_id, correction_type, action,
               relationship_type, source_node_name, target_node_name,
               original_semantic_type, new_semantic_type,
               confidence_score, applied_at, rolled_back
        FROM relationship_corrections
        ORDER BY applied_at DESC
        LIMIT $1
        """

        return await postgres_db.execute_query(query, [limit])

    @staticmethod
    async def can_rollback_correction(correction_id: str) -> bool:
        """Check if a correction can be rolled back."""
        postgres_db = await get_postgres_db()

        query = "SELECT can_rollback_correction($1) as can_rollback"
        result = await postgres_db.execute_query(query, [correction_id])

        return result[0]["can_rollback"] if result else False
