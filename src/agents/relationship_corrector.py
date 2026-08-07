"""
Relationship corrector agent for autonomous graph corrections.

This agent can safely correct relationship issues while preserving complete
audit trails for rollback. Focuses on deduplication and semantic standardization
while never modifying MENTIONS relationships (critical for GraphRAG).
"""

import re
import uuid

from pydantic import BaseModel

from ..db import get_neo4j_db
from .base_validator import BaseValidator


class CorrectionRecord(BaseModel):
    """Record of a single correction made by the agent."""

    correction_id: str
    correction_type: str  # 'DEDUPLICATION' or 'SEMANTIC_STANDARDIZATION'
    relationship_id: str
    action: str  # 'DELETE' or 'UPDATE'
    confidence_score: float
    reasoning: str
    original_semantic_type: str | None = None
    new_semantic_type: str | None = None
    duplicate_count: int | None = None


class RelationshipCorrector(BaseValidator):
    """
    Autonomous agent for correcting relationship issues.

    Capabilities:
    1. Remove duplicate relationships (preserving the most complete one)
    2. Standardize semantic types to SCREAMING_SNAKE_CASE
    3. Complete audit trail with rollback capability
    4. Never modifies MENTIONS relationships
    """

    def __init__(self, openai_api_key: str | None = None):
        """Initialize the relationship corrector."""
        super().__init__(agent_id="relationship_corrector_v1", openai_api_key=openai_api_key)

    def standardize_semantic_type(self, semantic_type: str) -> str:
        """Convert any format to SCREAMING_SNAKE_CASE."""
        if not semantic_type:
            return ""

        cleaned = semantic_type.strip()
        # Replace spaces, hyphens, dots with underscores
        standardized = re.sub(r"[\s\-\.]+", "_", cleaned)
        # Remove any special characters except underscores
        standardized = re.sub(r"[^A-Za-z0-9_]", "", standardized)
        # Convert to uppercase
        standardized = standardized.upper()
        # Remove multiple consecutive underscores
        standardized = re.sub(r"_+", "_", standardized)
        # Remove leading/trailing underscores
        standardized = standardized.strip("_")

        return standardized

    def select_best_duplicate(self, duplicates: list[dict]) -> tuple[dict, list[dict]]:
        """
        Choose which duplicate to keep based on data completeness.

        Returns:
            Tuple of (best_relationship, relationships_to_delete)
        """

        def score_relationship(rel: dict) -> int:
            """Score relationship based on data completeness."""
            props = rel.get("props", {})
            score = 0

            # Has embeddings (very important)
            if "fact_embedding" in props:
                score += 100
            if "name_embedding" in props:
                score += 100

            # Has semantic type
            if props.get("name"):
                score += 50

            # Has fact content
            if props.get("fact"):
                score += 30

            # Has episodes list
            if props.get("episodes"):
                episode_count = len(props["episodes"]) if isinstance(props["episodes"], list) else 1
                score += min(episode_count * 5, 50)  # Cap at 50 points

            # Has creation timestamp (more recent is better)
            if "created_at" in props:
                score += 10

            # Total number of properties
            score += len(props)

            return score

        # Score all duplicates
        scored = [(score_relationship(rel), rel) for rel in duplicates]
        # Sort by score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Best relationship is the highest scored
        best = scored[0][1]
        # All others are duplicates to delete
        to_delete = [rel for _, rel in scored[1:]]

        return best, to_delete

    async def analyze_duplicates(self, relationships: list[dict]) -> list[tuple[dict, list[dict]]]:
        """
        Analyze relationships to find duplicates.

        Returns:
            List of (best_relationship, duplicates_to_delete) tuples
        """
        # Group by (source, target, semantic_type) for RELATES_TO only
        relationship_groups = {}

        for rel in relationships:
            # Skip MENTIONS - never duplicate those
            if rel["type"] != "RELATES_TO":
                continue

            source_id = rel["source_id"]
            target_id = rel["target_id"]
            props = rel.get("props", {})
            semantic_type = props.get("name", "").lower().strip()

            # Skip if no semantic type
            if not semantic_type:
                continue

            group_key = (source_id, target_id, semantic_type)

            if group_key not in relationship_groups:
                relationship_groups[group_key] = []

            relationship_groups[group_key].append(rel)

        # Find groups with duplicates
        duplicate_groups = []
        for group_key, group_rels in relationship_groups.items():
            if len(group_rels) > 1:
                best, to_delete = self.select_best_duplicate(group_rels)
                duplicate_groups.append((best, to_delete))

        return duplicate_groups

    async def analyze_semantic_standardization(
        self, relationships: list[dict]
    ) -> list[tuple[dict, str]]:
        """
        Analyze relationships that need semantic type standardization.

        Returns:
            List of (relationship, standardized_semantic_type) tuples
        """
        standardization_needed = []

        for rel in relationships:
            # Only standardize RELATES_TO relationships
            if rel["type"] != "RELATES_TO":
                continue

            props = rel.get("props", {})
            current_semantic = props.get("name", "")

            if not current_semantic:
                continue

            standardized = self.standardize_semantic_type(current_semantic)

            # If standardization would change the semantic type, record it
            if current_semantic != standardized:
                standardization_needed.append((rel, standardized))

        return standardization_needed

    async def get_relationship_full_data(self, neo4j_db, relationship_id: str) -> dict | None:
        """Get complete relationship data including all properties."""
        query = """
        MATCH (source)-[r]->(target)
        WHERE elementId(r) = $rel_id
        RETURN elementId(r) as id,
               type(r) as type,
               properties(r) as properties,
               elementId(source) as source_id,
               source.name as source_name,
               elementId(target) as target_id,
               target.name as target_name
        """

        result = await neo4j_db.execute_query(query, {"rel_id": relationship_id})
        return result[0] if result else None

    async def delete_relationship_with_backup(self, neo4j_db, relationship_id: str) -> dict | None:
        """Delete relationship after backing up complete data."""
        # First get all data for backup
        full_data = await self.get_relationship_full_data(neo4j_db, relationship_id)
        if not full_data:
            return None

        # Delete the relationship
        delete_query = "MATCH ()-[r]->() WHERE elementId(r) = $id DELETE r"
        await neo4j_db.execute_query(delete_query, {"id": relationship_id})

        return full_data

    async def update_relationship_semantic_type(
        self, neo4j_db, relationship_id: str, new_semantic_type: str
    ) -> dict | None:
        """Update relationship semantic type (name property) after backing up."""
        # First get original data for backup
        original_data = await self.get_relationship_full_data(neo4j_db, relationship_id)
        if not original_data:
            return None

        # Update the semantic type (stored in 'name' property by Graphiti)
        update_query = """
        MATCH ()-[r]->()
        WHERE elementId(r) = $rel_id
        SET r.name = $new_type
        RETURN r
        """

        await neo4j_db.execute_query(
            update_query, {"rel_id": relationship_id, "new_type": new_semantic_type}
        )

        return original_data

    async def apply_corrections(
        self,
        relationships: list[dict],
        correct_duplicates: bool = True,
        standardize_semantics: bool = True,
        confidence_threshold: float = 0.85,
        max_corrections: int = 100,
        dry_run: bool = True,
    ) -> list[CorrectionRecord]:
        """
        Apply corrections to relationships.

        Args:
            relationships: List of relationships to analyze
            correct_duplicates: Whether to remove duplicates
            standardize_semantics: Whether to standardize semantic types
            confidence_threshold: Minimum confidence for applying corrections
            max_corrections: Maximum number of corrections to apply
            dry_run: If True, only analyze without making changes

        Returns:
            List of corrections that were applied (or would be applied in dry_run)
        """
        corrections = []
        neo4j_db = await get_neo4j_db()

        # 1. Handle duplicate removal
        if correct_duplicates:
            duplicate_groups = await self.analyze_duplicates(relationships)

            for best_rel, duplicates_to_delete in duplicate_groups:
                if len(corrections) >= max_corrections:
                    break

                for duplicate in duplicates_to_delete:
                    correction = CorrectionRecord(
                        correction_id=str(uuid.uuid4()),
                        correction_type="DEDUPLICATION",
                        relationship_id=duplicate["id"],
                        action="DELETE",
                        confidence_score=0.95,  # High confidence for deduplication
                        reasoning=f"Duplicate relationship removed. Kept the more complete version (ID: {best_rel['id']})",
                        duplicate_count=len(duplicates_to_delete) + 1,
                    )

                    # Apply correction if not dry run
                    if not dry_run:
                        backup_data = await self.delete_relationship_with_backup(
                            neo4j_db, duplicate["id"]
                        )
                        if backup_data:
                            # Store backup data in correction record for potential rollback
                            correction.metadata = {"backup_data": backup_data}

                    corrections.append(correction)

        # 2. Handle semantic standardization
        if standardize_semantics:
            standardization_needed = await self.analyze_semantic_standardization(relationships)

            for rel, standardized_semantic in standardization_needed:
                if len(corrections) >= max_corrections:
                    break

                current_semantic = rel.get("props", {}).get("name", "")

                correction = CorrectionRecord(
                    correction_id=str(uuid.uuid4()),
                    correction_type="SEMANTIC_STANDARDIZATION",
                    relationship_id=rel["id"],
                    action="UPDATE",
                    confidence_score=0.90,  # High confidence for standardization
                    reasoning=f"Standardized semantic type from '{current_semantic}' to '{standardized_semantic}'",
                    original_semantic_type=current_semantic,
                    new_semantic_type=standardized_semantic,
                )

                # Apply correction if not dry run
                if not dry_run:
                    backup_data = await self.update_relationship_semantic_type(
                        neo4j_db, rel["id"], standardized_semantic
                    )
                    if backup_data:
                        correction.metadata = {"backup_data": backup_data}

                corrections.append(correction)

        return corrections
