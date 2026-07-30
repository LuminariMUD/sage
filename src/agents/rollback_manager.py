"""
Rollback manager for relationship corrections.

Provides high-level interface for rolling back corrections made by the
autonomous validation agent. Handles both individual corrections and
batch rollbacks with comprehensive audit trails.
"""

from datetime import datetime
from typing import Any

from ..db import get_postgres_db
from .correction_storage import CorrectionStorageService


class RollbackManager:
    """Manager for rolling back relationship corrections."""

    @staticmethod
    async def rollback_correction(
        correction_id: str, rollback_by: str, rollback_reason: str = "Manual rollback requested"
    ) -> dict[str, Any]:
        """
        Rollback a single correction.

        Args:
            correction_id: ID of the correction to rollback
            rollback_by: Who is performing the rollback
            rollback_reason: Why the rollback is being performed

        Returns:
            Dictionary with rollback result and details
        """
        # Check if correction can be rolled back
        can_rollback = await CorrectionStorageService.can_rollback_correction(correction_id)
        if not can_rollback:
            return {
                "success": False,
                "error": "Correction cannot be rolled back (not found or already rolled back)",
                "correction_id": correction_id,
            }

        # Get correction details for response
        correction = await CorrectionStorageService.get_correction(correction_id)
        if not correction:
            return {
                "success": False,
                "error": "Correction not found",
                "correction_id": correction_id,
            }

        # Perform rollback
        success = await CorrectionStorageService.rollback_correction(
            correction_id, rollback_by, rollback_reason
        )

        result = {
            "success": success,
            "correction_id": correction_id,
            "correction_type": correction["correction_type"],
            "action": correction["action"],
            "relationship_id": correction["relationship_id"],
            "rollback_by": rollback_by,
            "rollback_reason": rollback_reason,
            "rollback_timestamp": datetime.utcnow().isoformat(),
        }

        if success:
            result["message"] = (
                f"Successfully rolled back {correction['correction_type']} correction"
            )
            if correction["action"] == "DELETE":
                result[
                    "message"
                ] += f" (restored deleted relationship {correction['relationship_id']})"
            elif correction["action"] == "UPDATE":
                result[
                    "message"
                ] += f" (restored original semantic type '{correction['original_semantic_type']}')"
        else:
            result["error"] = "Failed to rollback correction"

        return result

    @staticmethod
    async def rollback_batch(
        correction_batch_id: str,
        rollback_by: str,
        rollback_reason: str = "Batch rollback requested",
    ) -> dict[str, Any]:
        """
        Rollback all corrections in a batch.

        Args:
            correction_batch_id: ID of the batch to rollback
            rollback_by: Who is performing the rollback
            rollback_reason: Why the rollback is being performed

        Returns:
            Dictionary with batch rollback results and statistics
        """
        # Get batch summary before rollback
        batch_summary = await CorrectionStorageService.get_correction_batch_summary(
            correction_batch_id
        )
        if not batch_summary or batch_summary["total_corrections"] == 0:
            return {
                "success": False,
                "error": "Correction batch not found or empty",
                "correction_batch_id": correction_batch_id,
            }

        # Perform batch rollback
        rollback_stats = await CorrectionStorageService.rollback_batch(
            correction_batch_id, rollback_by, rollback_reason
        )

        success = rollback_stats["failed"] == 0 and rollback_stats["successful"] > 0

        return {
            "success": success,
            "correction_batch_id": correction_batch_id,
            "rollback_by": rollback_by,
            "rollback_reason": rollback_reason,
            "rollback_timestamp": datetime.utcnow().isoformat(),
            "statistics": {
                "total_corrections_in_batch": rollback_stats["total"],
                "successfully_rolled_back": rollback_stats["successful"],
                "failed_to_rollback": rollback_stats["failed"],
                "already_rolled_back": rollback_stats["already_rolled_back"],
            },
            "original_batch_summary": batch_summary,
            "message": f"Rolled back {rollback_stats['successful']} of {rollback_stats['total']} corrections",
        }

    @staticmethod
    async def rollback_validation_report(
        validation_report_id: str,
        rollback_by: str,
        rollback_reason: str = "Validation report rollback requested",
    ) -> dict[str, Any]:
        """
        Rollback all corrections associated with a validation report.

        Args:
            validation_report_id: ID of the validation report
            rollback_by: Who is performing the rollback
            rollback_reason: Why the rollback is being performed

        Returns:
            Dictionary with rollback results
        """
        # Get corrections for this report
        corrections = await CorrectionStorageService.get_corrections_for_report(
            validation_report_id
        )

        if not corrections:
            return {
                "success": False,
                "error": "No corrections found for validation report",
                "validation_report_id": validation_report_id,
            }

        # Group corrections by batch and rollback each batch
        batches = {}
        for correction in corrections:
            batch_id = correction["correction_batch_id"]
            if batch_id not in batches:
                batches[batch_id] = []
            batches[batch_id].append(correction)

        rollback_results = []
        total_successful = 0
        total_failed = 0

        for batch_id in batches:
            batch_result = await RollbackManager.rollback_batch(
                batch_id, rollback_by, rollback_reason
            )
            rollback_results.append(batch_result)
            if batch_result.get("statistics"):
                total_successful += batch_result["statistics"]["successfully_rolled_back"]
                total_failed += batch_result["statistics"]["failed_to_rollback"]

        return {
            "success": total_failed == 0 and total_successful > 0,
            "validation_report_id": validation_report_id,
            "rollback_by": rollback_by,
            "rollback_reason": rollback_reason,
            "rollback_timestamp": datetime.utcnow().isoformat(),
            "statistics": {
                "total_batches": len(batches),
                "total_corrections": len(corrections),
                "successfully_rolled_back": total_successful,
                "failed_to_rollback": total_failed,
            },
            "batch_results": rollback_results,
            "message": f"Processed {len(batches)} correction batches with {total_successful} successful rollbacks",
        }

    @staticmethod
    async def get_rollback_history(limit: int = 100) -> list[dict[str, Any]]:
        """Get history of rollbacks for monitoring."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT correction_id, correction_batch_id, correction_type, action,
               relationship_id, relationship_type,
               source_node_name, target_node_name,
               original_semantic_type, new_semantic_type,
               applied_at, rollback_at, rollback_by, rollback_reason,
               confidence_score
        FROM relationship_corrections
        WHERE rolled_back = TRUE
        ORDER BY rollback_at DESC
        LIMIT $1
        """

        return await postgres_db.execute_query(query, [limit])

    @staticmethod
    async def get_rollback_statistics(days: int = 30) -> dict[str, Any]:
        """Get rollback statistics for the specified number of days."""
        postgres_db = await get_postgres_db()

        query = """
        SELECT
            COUNT(*) as total_rollbacks,
            COUNT(*) FILTER (WHERE correction_type = 'DEDUPLICATION') as dedup_rollbacks,
            COUNT(*) FILTER (WHERE correction_type = 'SEMANTIC_STANDARDIZATION') as semantic_rollbacks,
            COUNT(*) FILTER (WHERE action = 'DELETE') as delete_rollbacks,
            COUNT(*) FILTER (WHERE action = 'UPDATE') as update_rollbacks,
            COUNT(DISTINCT correction_batch_id) as batches_rolled_back,
            COUNT(DISTINCT rollback_by) as unique_rollback_users,
            -- confidence_score is double precision, and round(double precision, int) does
            -- not exist in PostgreSQL; the cast to numeric is required.
            ROUND(AVG(confidence_score)::numeric, 3) as avg_confidence_of_rolled_back
        FROM relationship_corrections
        WHERE rolled_back = TRUE
        -- make_interval() takes a real bind parameter. INTERVAL '$1 days' does not:
        -- the $1 sits inside a string literal, so it is never bound.
        AND rollback_at >= NOW() - make_interval(days => $1)
        """

        result = await postgres_db.execute_query(query, [days])
        return result[0] if result else {}

    @staticmethod
    async def preview_rollback_batch(correction_batch_id: str) -> dict[str, Any]:
        """Preview what would be rolled back in a batch without actually doing it."""
        corrections = await CorrectionStorageService.get_corrections_for_batch(correction_batch_id)

        if not corrections:
            return {
                "success": False,
                "error": "Correction batch not found",
                "correction_batch_id": correction_batch_id,
            }

        preview = {
            "success": True,
            "correction_batch_id": correction_batch_id,
            "total_corrections": len(corrections),
            "corrections_preview": [],
        }

        for correction in corrections:
            if correction.get("rolled_back"):
                continue  # Skip already rolled back

            correction_preview = {
                "correction_id": correction["correction_id"],
                "correction_type": correction["correction_type"],
                "action": correction["action"],
                "relationship_id": correction["relationship_id"],
                "confidence_score": correction["confidence_score"],
                "applied_at": (
                    correction["applied_at"].isoformat() if correction.get("applied_at") else None
                ),
            }

            if correction["action"] == "DELETE":
                correction_preview["rollback_action"] = "Restore deleted relationship"
                correction_preview["affected_entities"] = (
                    f"{correction['source_node_name']} → {correction['target_node_name']}"
                )
            elif correction["action"] == "UPDATE":
                correction_preview["rollback_action"] = (
                    f"Restore semantic type from '{correction['new_semantic_type']}' back to '{correction['original_semantic_type']}'"
                )

            preview["corrections_preview"].append(correction_preview)

        preview["rollbackable_corrections"] = len(preview["corrections_preview"])
        return preview
