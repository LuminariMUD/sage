"""
Relationship validator agent for Luminari Sage knowledge graph.

This agent validates entity relationships in the Neo4j graph database, focusing on
RELATES_TO and MENTIONS edges with semantic meaning encoded in properties.
Performs bidirectional consistency checks, mutual exclusivity validation,
and hierarchy rule enforcement.
"""

import os
import time
import uuid
from typing import Literal

from pydantic import BaseModel

from ..db import get_neo4j_db
from .base_validator import BaseValidator, ValidationFinding, ValidationReport, ValidationSeverity
from .correction_storage import CorrectionStorageService
from .relationship_corrector import RelationshipCorrector
from .validation_storage import ValidationStorageService


class SemanticAnalysis(BaseModel):
    """Single relationship semantic analysis result."""

    relationship_id: str
    semantic_appropriateness: Literal["APPROPRIATE", "QUESTIONABLE", "INAPPROPRIATE"]
    source_entity_type: str
    target_entity_type: str
    current_relationship: str
    suggested_relationship: str
    suggested_reverse_relationship: str | None = None
    bidirectional_assessment: Literal[
        "NATURALLY_BIDIRECTIONAL", "NATURALLY_UNIDIRECTIONAL", "CONTEXT_DEPENDENT"
    ]
    reasoning: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class SemanticAnalysisResponse(BaseModel):
    """Response structure for relationship semantic analysis."""

    analyses: list[SemanticAnalysis]


class RelatesToAnalysis(BaseModel):
    """Single RELATES_TO relationship analysis result."""

    relationship_id: str
    semantic_clarity: Literal["CLEAR", "UNCLEAR", "MISSING"]
    suggested_semantic_type: str
    graphrag_impact: Literal["HIGH", "MEDIUM", "LOW"]
    llm_reasoning: str


class RelatesAnalysisResponse(BaseModel):
    """Response structure for RELATES_TO analysis."""

    analyses: list[RelatesToAnalysis]


class MentionsAnalysis(BaseModel):
    """Single MENTIONS relationship analysis result."""

    relationship_id: str
    optimal_type: Literal["MENTIONS", "RELATES_TO"]
    graphrag_benefit: Literal["CLEAR_SEPARATION", "IMPROVED_REASONING", "NEUTRAL"]
    semantic_richness: Literal["HIGH_VALUE", "SOME_VALUE", "MINIMAL_VALUE"]
    llm_strategy: str


class MentionsAnalysisResponse(BaseModel):
    """Response structure for MENTIONS analysis."""

    analyses: list[MentionsAnalysis]


class RelationshipValidator(BaseValidator):
    """
    Validates entity relationships in the knowledge graph.

    Focuses on RELATES_TO and MENTIONS edges, analyzing semantic properties
    to identify consistency issues, missing bidirectional relationships,
    and logical contradictions.
    """

    def __init__(self, openai_api_key: str):
        """Initialize the relationship validator."""
        super().__init__(agent_id="relationship_validator_v1_llm", openai_api_key=openai_api_key)

        # Define validation rules - these apply to RELATES_TO relationships only
        # MENTIONS relationships are simple episode-to-entity links (no bidirectionality needed)
        self.bidirectional_relationships = {
            "allied_with",
            "opposed_to",
            "related_to",
            "connected_to",
            "married_to",
            "sibling_of",
            "friend_of",
            "enemy_of",
        }

        self.mutual_exclusive_relationships = {
            ("allied_with", "opposed_to"),
            ("friend_of", "enemy_of"),
            ("protects", "threatens"),
            ("supports", "opposes"),
        }

        self.hierarchical_relationships = {
            "commands": "serves_under",
            "rules": "governed_by",
            "created_by": "creation_of",
            "parent_of": "child_of",
            "teaches": "student_of",
        }

    async def validate(
        self,
        entity_limit: int = 1000,
        relationship_limit: int = 5000,
        check_bidirectional: bool = True,
        check_mutual_exclusivity: bool = True,
        check_hierarchies: bool = True,
        check_semantic_consistency: bool = True,
        enable_llm_analysis: bool = True,
        # Autonomous correction parameters
        auto_correct: bool = False,
        correct_duplicates: bool = True,
        standardize_semantics: bool = True,
        confidence_threshold: float = 0.85,
        max_corrections: int = 100,
        dry_run: bool = True,
    ) -> ValidationReport:
        """
        Perform comprehensive relationship validation with optional autonomous corrections.

        Args:
            entity_limit: Maximum entities to check
            relationship_limit: Maximum relationships to analyze
            check_bidirectional: Whether to check bidirectional consistency
            check_mutual_exclusivity: Whether to check mutually exclusive relationships
            check_hierarchies: Whether to validate hierarchical relationships
            check_semantic_consistency: Whether to check semantic property consistency
            enable_llm_analysis: Whether to enhance semantic findings with LLM analysis

            auto_correct: Enable autonomous corrections for high-confidence issues
            correct_duplicates: Whether to remove duplicate relationships
            standardize_semantics: Whether to standardize semantic types to SCREAMING_SNAKE_CASE
            confidence_threshold: Minimum confidence required for auto-correction
            max_corrections: Maximum number of corrections to apply
            dry_run: If True, only preview corrections without applying them
        """
        start_time = time.time()
        findings = []
        total_items_checked = 0

        try:
            neo4j_db = await get_neo4j_db()

            # Get entities and relationships to analyze
            entities, relationships = await self._fetch_graph_data(
                neo4j_db, entity_limit, relationship_limit
            )

            total_items_checked = len(entities) + len(relationships)

            if check_bidirectional:
                bidirectional_findings = await self._check_bidirectional_consistency(relationships)
                findings.extend(bidirectional_findings)

            if check_mutual_exclusivity:
                exclusivity_findings = await self._check_mutual_exclusivity(relationships)
                findings.extend(exclusivity_findings)

            if check_hierarchies:
                hierarchy_findings = await self._check_hierarchical_consistency(relationships)
                findings.extend(hierarchy_findings)

            if check_semantic_consistency:
                semantic_findings = await self._check_semantic_consistency(relationships)
                findings.extend(semantic_findings)

                # Enhanced LLM analysis for semantic consistency issues
                if semantic_findings and enable_llm_analysis:
                    llm_enhanced_findings = await self._enhance_semantic_findings_with_llm(
                        semantic_findings, relationships
                    )
                    findings.extend(llm_enhanced_findings)

            # Additional validation checks
            orphan_findings = await self._check_orphaned_entities(entities, relationships)
            findings.extend(orphan_findings)

            duplicate_findings = await self._check_duplicate_relationships(relationships)
            findings.extend(duplicate_findings)

            execution_time = time.time() - start_time

            report = self.create_report(
                validation_type="Entity Relationship Validation",
                scope_description=f"Analyzed {len(entities)} entities and {len(relationships)} relationships",
                total_items_checked=total_items_checked,
                findings=findings,
                execution_time_seconds=execution_time,
                success=True,
            )

            # Apply autonomous corrections if requested
            corrections_applied = []
            correction_batch_id = None

            if auto_correct:
                correction_batch_id = str(uuid.uuid4())
                openai_api_key = os.getenv("OPENAI_API_KEY")
                if not openai_api_key:
                    raise RuntimeError("OpenAI API key is not configured")
                corrector = RelationshipCorrector(openai_api_key=openai_api_key)

                try:
                    corrections_applied = await corrector.apply_corrections(
                        relationships=relationships,
                        correct_duplicates=correct_duplicates,
                        standardize_semantics=standardize_semantics,
                        confidence_threshold=confidence_threshold,
                        max_corrections=max_corrections,
                        dry_run=dry_run,
                    )

                    # Store correction records in PostgreSQL
                    for correction in corrections_applied:
                        if hasattr(correction, "metadata") and correction.metadata:
                            await CorrectionStorageService.store_correction(
                                correction_id=correction.correction_id,
                                validation_report_id=report.report_id,
                                correction_batch_id=correction_batch_id,
                                correction_type=correction.correction_type,
                                action=correction.action,
                                confidence_score=correction.confidence_score,
                                agent_reasoning=correction.reasoning,
                                relationship_data=correction.metadata["backup_data"],
                                original_semantic_type=correction.original_semantic_type,
                                new_semantic_type=correction.new_semantic_type,
                                duplicate_count=correction.duplicate_count,
                            )

                except Exception as correction_error:
                    print(
                        f"Warning: Failed to apply corrections ({type(correction_error).__name__})"
                    )

            # Enhance report with correction information
            report.metadata = report.metadata or {}
            report.metadata.update(
                {
                    "auto_correction_enabled": auto_correct,
                    "corrections_applied": len(corrections_applied),
                    "correction_batch_id": correction_batch_id,
                    "duplicates_removed": len(
                        [c for c in corrections_applied if c.correction_type == "DEDUPLICATION"]
                    ),
                    "semantics_standardized": len(
                        [
                            c
                            for c in corrections_applied
                            if c.correction_type == "SEMANTIC_STANDARDIZATION"
                        ]
                    ),
                    "dry_run": dry_run,
                }
            )

            # Store the report in PostgreSQL for audit trail
            try:
                await ValidationStorageService.store_report(report)
            except Exception as storage_error:
                # Log but don't fail the validation if storage fails
                print(
                    f"Warning: failed to store validation report ({type(storage_error).__name__})"
                )

            return report

        except Exception as e:
            execution_time = time.time() - start_time
            error_report = self.create_report(
                validation_type="Entity Relationship Validation",
                scope_description="Validation failed due to error",
                total_items_checked=total_items_checked,
                findings=findings,
                execution_time_seconds=execution_time,
                success=False,
                error_message=f"Validation failed ({type(e).__name__})",
            )

            # Store the error report as well for debugging
            try:
                await ValidationStorageService.store_report(error_report)
            except Exception as storage_error:
                print(
                    "Warning: failed to store error validation report "
                    f"({type(storage_error).__name__})"
                )

            return error_report

    async def _fetch_graph_data(
        self, neo4j_db, entity_limit: int, relationship_limit: int
    ) -> tuple[list[dict], list[dict]]:
        """Fetch entities and relationships from Neo4j, ensuring relationships correspond to fetched entities."""

        # Get entities with their properties
        entity_query = """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ['Entity', 'Episodic'])
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as props
        LIMIT $limit
        """

        entity_result = await neo4j_db.execute_query(
            entity_query, parameters={"limit": entity_limit}
        )

        entities = entity_result  # execute_query already returns List[Dict]

        # Extract entity IDs for relationship filtering
        entity_ids = [entity["id"] for entity in entities]

        # Get relationships ONLY for the entities we're validating
        # This ensures we get relationships for the specific entities, not just any random relationships
        relationship_query = """
        MATCH (a)-[r]->(b)
        WHERE elementId(a) IN $entity_ids AND elementId(b) IN $entity_ids
        AND any(label IN labels(a) WHERE label IN ['Entity', 'Episodic'])
        AND any(label IN labels(b) WHERE label IN ['Entity', 'Episodic'])
        RETURN elementId(r) as id, type(r) as type, properties(r) as props,
               elementId(a) as source_id, a.name as source_name, labels(a) as source_labels,
               elementId(b) as target_id, b.name as target_name, labels(b) as target_labels
        LIMIT $limit
        """

        relationship_result = await neo4j_db.execute_query(
            relationship_query, parameters={"entity_ids": entity_ids, "limit": relationship_limit}
        )

        relationships = relationship_result  # execute_query already returns List[Dict]

        # Log what we're validating for debugging
        entity_names = [e.get("props", {}).get("name", "Unknown") for e in entities]
        print(
            f"Validating {len(entities)} entities: {entity_names[:5]}{'...' if len(entity_names) > 5 else ''}"
        )
        print(f"Found {len(relationships)} relationships between these entities")

        return entities, relationships

    async def _check_bidirectional_consistency(
        self, relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Check for semantic appropriateness of relationships and suggest better alternatives."""
        findings = []

        # Collect RELATES_TO relationships for semantic analysis
        relates_to_relationships = []
        relationship_pairs = {}

        for rel in relationships:
            source_id = rel["source_id"]
            target_id = rel["target_id"]
            rel_type = rel["type"]
            rel_props = rel.get("props", {})

            # Business rule: Only analyze RELATES_TO relationships
            if rel_type != "RELATES_TO":
                continue

            # Get semantic relationship type from properties
            semantic_type = self._extract_semantic_type(rel_props)

            if semantic_type:
                relates_to_relationships.append(
                    {
                        "rel_id": rel["id"],
                        "source_id": source_id,
                        "target_id": target_id,
                        "semantic_type": semantic_type,
                        "source_name": rel.get("source_name", "Unknown"),
                        "target_name": rel.get("target_name", "Unknown"),
                        "properties": rel_props,
                    }
                )

                # Still group by pairs for traditional bidirectional checking
                pair_key = tuple(sorted([source_id, target_id]))
                if pair_key not in relationship_pairs:
                    relationship_pairs[pair_key] = []
                relationship_pairs[pair_key].append(
                    {
                        "rel_id": rel["id"],
                        "source": source_id,
                        "target": target_id,
                        "semantic_type": semantic_type,
                        "source_name": rel.get("source_name", "Unknown"),
                        "target_name": rel.get("target_name", "Unknown"),
                    }
                )

        # Semantic analysis with LLM for relationship appropriateness
        if relates_to_relationships:
            semantic_findings = await self._analyze_relationship_semantics(relates_to_relationships)
            findings.extend(semantic_findings)

        # Traditional bidirectional check for obviously bidirectional relationships
        simple_bidirectional = {
            "allied_with",
            "married_to",
            "sibling_of",
            "friend_of",
            "enemy_of",
            "opposed_to",
        }
        for pair_key, pair_rels in relationship_pairs.items():
            if len(pair_rels) == 1:
                rel = pair_rels[0]
                semantic_lower = rel["semantic_type"].lower().replace(" ", "_")

                # Only flag clearly bidirectional relationships for traditional check
                if semantic_lower in simple_bidirectional:
                    finding = self.create_finding(
                        severity=ValidationSeverity.INFO,
                        category="bidirectional_consistency",
                        title=f"Potentially missing bidirectional RELATES_TO: {rel['semantic_type']}",
                        description=f"Found RELATES_TO {rel['semantic_type']} relationship from {rel['source_name']} to {rel['target_name']}, which typically should be bidirectional.",
                        confidence_score=0.6,
                        confidence_explanation="Medium confidence - some relationship types are naturally bidirectional, but semantic context matters",
                        suggested_action=f"Review if reverse {rel['semantic_type']} relationship from {rel['target_name']} to {rel['source_name']} should exist",
                        priority=3,
                        evidence=[
                            f"Relationship ID: {rel['rel_id']}",
                            f"Semantic type: {rel['semantic_type']}",
                            f"Direction: {rel['source_name']} → {rel['target_name']}",
                            "Note: Semantic analysis will provide more detailed recommendations",
                        ],
                        affected_entities=[rel["source"], rel["target"]],
                        affected_relationships=[rel["rel_id"]],
                    )
                    findings.append(finding)

        return findings

    async def _check_mutual_exclusivity(self, relationships: list[dict]) -> list[ValidationFinding]:
        """Check for mutually exclusive relationships between same entities."""
        findings = []

        # Group relationships by entity pairs
        entity_relationships = {}

        for rel in relationships:
            source_id = rel["source_id"]
            target_id = rel["target_id"]
            rel_type = rel["type"]
            rel_props = rel.get("props", {})
            semantic_type = self._extract_semantic_type(rel_props)

            # Business rule: Only check mutual exclusivity for RELATES_TO relationships
            # MENTIONS are simple episode-to-entity links (no mutual exclusivity issues)
            if rel_type != "RELATES_TO" or not semantic_type:
                continue

            pair_key = (source_id, target_id)

            if pair_key not in entity_relationships:
                entity_relationships[pair_key] = []

            entity_relationships[pair_key].append(
                {
                    "rel_id": rel["id"],
                    "semantic_type": semantic_type.lower(),
                    "source_name": rel.get("source_name", "Unknown"),
                    "target_name": rel.get("target_name", "Unknown"),
                }
            )

        # Check for mutually exclusive relationships
        for pair_key, pair_rels in entity_relationships.items():
            if len(pair_rels) < 2:
                continue

            semantic_types = {rel["semantic_type"] for rel in pair_rels}

            # Check each mutual exclusivity rule
            for exclusive_pair in self.mutual_exclusive_relationships:
                type1, type2 = exclusive_pair

                if type1 in semantic_types and type2 in semantic_types:
                    conflicting_rels = [
                        rel for rel in pair_rels if rel["semantic_type"] in exclusive_pair
                    ]

                    finding = self.create_finding(
                        severity=ValidationSeverity.ERROR,
                        category="mutual_exclusivity",
                        title=f"Mutually exclusive RELATES_TO: {type1} vs {type2}",
                        description=f"Entities {conflicting_rels[0]['source_name']} and {conflicting_rels[0]['target_name']} have both RELATES_TO '{type1}' and '{type2}' relationships, which are mutually exclusive.",
                        confidence_score=0.9,
                        confidence_explanation="Very high confidence - these RELATES_TO relationship types are logically contradictory. MENTIONS relationships don't have mutual exclusivity issues.",
                        suggested_action="Review and remove one of the conflicting RELATES_TO relationships, or reclassify if the situation is more complex",
                        priority=1,
                        evidence=[
                            f"RELATES_TO Relationship 1: {type1} (ID: {conflicting_rels[0]['rel_id']})",
                            f"RELATES_TO Relationship 2: {type2} (ID: {conflicting_rels[1]['rel_id']})",
                            f"Between: {conflicting_rels[0]['source_name']} and {conflicting_rels[0]['target_name']}",
                            "Business rule: Only RELATES_TO has mutual exclusivity rules, MENTIONS do not",
                        ],
                        affected_relationships=[rel["rel_id"] for rel in conflicting_rels],
                    )
                    findings.append(finding)

        return findings

    async def _check_hierarchical_consistency(
        self, relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Check hierarchical relationship consistency."""
        findings = []

        # Group relationships by semantic type
        semantic_relationships = {}

        for rel in relationships:
            rel_props = rel.get("props", {})
            semantic_type = self._extract_semantic_type(rel_props)

            if not semantic_type:
                continue

            semantic_type = semantic_type.lower()

            if semantic_type not in semantic_relationships:
                semantic_relationships[semantic_type] = []

            semantic_relationships[semantic_type].append(
                {
                    "rel_id": rel["id"],
                    "source_id": rel["source_id"],
                    "target_id": rel["target_id"],
                    "source_name": rel.get("source_name", "Unknown"),
                    "target_name": rel.get("target_name", "Unknown"),
                }
            )

        # Check hierarchical consistency
        for parent_type, child_type in self.hierarchical_relationships.items():
            parent_rels = semantic_relationships.get(parent_type, [])
            child_rels = semantic_relationships.get(child_type, [])

            if not parent_rels or not child_rels:
                continue

            # Create lookup for child relationships
            child_lookup = {(rel["source_id"], rel["target_id"]): rel for rel in child_rels}

            # Check each parent relationship for corresponding child relationship
            for parent_rel in parent_rels:
                expected_child_key = (parent_rel["target_id"], parent_rel["source_id"])

                if expected_child_key not in child_lookup:
                    finding = self.create_finding(
                        severity=ValidationSeverity.INFO,
                        category="hierarchical_consistency",
                        title=f"Missing hierarchical counterpart: {parent_type} → {child_type}",
                        description=f"Found '{parent_type}' relationship from {parent_rel['source_name']} to {parent_rel['target_name']}, but missing corresponding '{child_type}' relationship in reverse.",
                        confidence_score=0.7,
                        confidence_explanation="High confidence - hierarchical relationships typically have inverse counterparts",
                        suggested_action=f"Consider adding '{child_type}' relationship from {parent_rel['target_name']} to {parent_rel['source_name']}",
                        priority=3,
                        evidence=[
                            f"Parent relationship: {parent_type} (ID: {parent_rel['rel_id']})",
                            f"Expected child relationship: {child_type}",
                            f"Direction: {parent_rel['source_name']} {parent_type} {parent_rel['target_name']}",
                        ],
                        affected_entities=[parent_rel["source_id"], parent_rel["target_id"]],
                        affected_relationships=[parent_rel["rel_id"]],
                    )
                    findings.append(finding)

        return findings

    async def _check_semantic_consistency(
        self, relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Check semantic property consistency in relationships."""
        findings = []

        for rel in relationships:
            rel_props = rel.get("props", {})
            semantic_type = self._extract_semantic_type(rel_props)
            rel_type = rel["type"]

            # Business rule: Only RELATES_TO needs rich semantic attributes
            # MENTIONS just links episodes to entities (no semantic validation needed)
            if rel_type == "RELATES_TO":
                # Check if semantic type exists for RELATES_TO
                if not semantic_type:
                    finding = self.create_finding(
                        severity=ValidationSeverity.WARNING,
                        category="llm_understanding",
                        title="RELATES_TO lacks semantic clarity for LLM reasoning",
                        description=f"RELATES_TO relationship between {rel.get('source_name', 'Unknown')} and {rel.get('target_name', 'Unknown')} lacks semantic type information needed for hybrid GraphRAG. LLMs need semantic context to understand relationship meaning.",
                        confidence_score=0.8,
                        confidence_explanation="High confidence - LLMs require semantic context for effective graph reasoning in hybrid GraphRAG systems",
                        suggested_action="Add semantic type that helps LLM understand relationship meaning (e.g., 'allied_with', 'commands', 'protects')",
                        priority=2,
                        evidence=[
                            f"Relationship ID: {rel['id']}",
                            f"Relationship type: {rel_type}",
                            f"Properties: {rel_props}",
                            "GraphRAG optimization: RELATES_TO needs semantic context for LLM understanding",
                        ],
                        affected_relationships=[rel["id"]],
                    )
                    findings.append(finding)
            elif rel_type == "MENTIONS":
                # MENTIONS relationships should NOT have complex semantic attributes
                # They're just simple episode-to-entity links
                if semantic_type and semantic_type not in ["mentions", "references", "appears_in"]:
                    finding = self.create_finding(
                        severity=ValidationSeverity.INFO,
                        category="graphrag_optimization",
                        title="MENTIONS may have rich semantics suitable for RELATES_TO",
                        description=f"MENTIONS relationship between {rel.get('source_name', 'Unknown')} and {rel.get('target_name', 'Unknown')} has semantic type '{semantic_type}'. This semantic richness might provide more value as RELATES_TO for LLM graph reasoning.",
                        confidence_score=0.6,
                        confidence_explanation="Medium confidence - rich semantics in MENTIONS may indicate better classification as RELATES_TO for GraphRAG",
                        suggested_action="Consider converting to RELATES_TO to leverage semantic richness for LLM graph traversal",
                        priority=3,
                        evidence=[
                            f"Relationship ID: {rel['id']}",
                            f"Relationship type: {rel_type}",
                            f"Semantic type: {semantic_type}",
                            "GraphRAG optimization: Rich semantics may be better classified as RELATES_TO",
                        ],
                        affected_relationships=[rel["id"]],
                    )
                    findings.append(finding)

            # Formatting validation completely removed - LLM will understand semantic meaning regardless of format
            # Focus only on semantic understanding for hybrid GraphRAG compatibility

        return findings

    async def _analyze_relationship_semantics(
        self, relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Use LLM to analyze relationship semantics and suggest improvements."""
        findings = []

        try:
            # Batch relationships for LLM analysis (process in groups of 10)
            batch_size = 10
            for i in range(0, len(relationships), batch_size):
                batch = relationships[i : i + batch_size]

                # Create LLM prompt for semantic analysis
                prompt = self._create_semantic_analysis_prompt(batch)

                # Run LLM analysis with structured output
                result = await self.agent.run(prompt, output_type=SemanticAnalysisResponse)

                # Process structured response and create findings
                batch_findings = self._process_semantic_analysis(result.output, batch)
                findings.extend(batch_findings)

        except Exception as e:
            # If LLM analysis fails, create a failure finding but don't break validation
            error_type = type(e).__name__
            findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_semantic_analysis",
                    title="LLM semantic analysis failed",
                    description="Could not analyze relationship semantics with the LLM",
                    confidence_score=0.9,
                    confidence_explanation="High confidence - LLM failure doesn't affect other validation rules",
                    suggested_action="Review relationships manually or check LLM configuration",
                    priority=4,
                    evidence=[f"LLM error type: {error_type}"],
                )
            )

        return findings

    def _create_semantic_analysis_prompt(self, relationships: list[dict]) -> str:
        """Create LLM prompt for analyzing relationship semantics."""
        relationships_text = ""
        for i, rel in enumerate(relationships, 1):
            relationships_text += f"""
{i}. {rel["source_name"]} --{rel["semantic_type"]}--> {rel["target_name"]}
   Relationship ID: {rel["rel_id"]}
   Properties: {", ".join([f"{k}: {v}" for k, v in rel["properties"].items() if k not in ["embedding", "fact_embedding"]])}
"""

        return f"""Analyze these RELATES_TO relationships for semantic appropriateness and suggest improvements.

You are optimizing a hybrid GraphRAG system. Focus on whether relationships make semantic sense between the entity types, and suggest better relationship types when appropriate.

RELATIONSHIPS TO ANALYZE:
{relationships_text}

For each relationship, analyze:

1. SEMANTIC_APPROPRIATENESS: Does this relationship type make sense between these entities?
   - APPROPRIATE: Relationship makes perfect semantic sense
   - QUESTIONABLE: Relationship is odd but might be valid in context
   - INAPPROPRIATE: Relationship type doesn't fit these entity types

2. ENTITY_TYPE_ANALYSIS: What types of entities are these?
   - Examples: PERSON, ORGANIZATION, PLACE, OBJECT, CONCEPT, MATERIAL, FACTION

3. SUGGESTED_IMPROVEMENT: If inappropriate/questionable, what would be better?
   - Better relationship type for this entity pair
   - Whether bidirectionality makes sense
   - What the reverse relationship should be (if any)

4. BIDIRECTIONAL_ASSESSMENT: Should this relationship be bidirectional?
   - NATURALLY_BIDIRECTIONAL: Like "married_to", "allied_with", "sibling_of"
   - NATURALLY_UNIDIRECTIONAL: Like "created_by", "uses", "commands"
   - CONTEXT_DEPENDENT: Depends on the specific situation

Examples of common issues to flag:
- Factions "commanding" materials (should be "uses")
- People "allied with" concepts (should be "believes_in" or "supports")
- Places "married to" people (should be "inhabited_by" or person "lives_in" place)
- Objects "commanding" people (should be person "wields" or "owns" object)

Provide your analysis for each relationship."""

    def _process_semantic_analysis(
        self, response_data: SemanticAnalysisResponse, relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Process structured LLM semantic analysis and create findings."""
        findings = []

        try:
            for analysis in response_data.analyses:
                rel_id = analysis.relationship_id

                # Find the original relationship
                rel = next((r for r in relationships if r["rel_id"] == rel_id), None)
                if not rel:
                    continue

                appropriateness = analysis.semantic_appropriateness
                confidence_str = analysis.confidence

                # Only create findings for questionable or inappropriate relationships
                if appropriateness in ["QUESTIONABLE", "INAPPROPRIATE"]:
                    severity_map = {
                        "INAPPROPRIATE": ValidationSeverity.WARNING,
                        "QUESTIONABLE": ValidationSeverity.INFO,
                    }

                    confidence_map = {"HIGH": 0.8, "MEDIUM": 0.6, "LOW": 0.4}

                    severity = severity_map.get(appropriateness, ValidationSeverity.INFO)
                    confidence = confidence_map.get(confidence_str, 0.6)

                    # Create title based on the issue
                    if appropriateness == "INAPPROPRIATE":
                        title = f"Semantically inappropriate relationship: {rel['source_name']} {analysis.current_relationship} {rel['target_name']}"
                    else:
                        title = f"Questionable relationship semantics: {rel['source_name']} {analysis.current_relationship} {rel['target_name']}"

                    # Build suggestion
                    suggested_action = f"Consider changing to: {rel['source_name']} {analysis.suggested_relationship} {rel['target_name']}"
                    if analysis.suggested_reverse_relationship:
                        suggested_action += f" and {rel['target_name']} {analysis.suggested_reverse_relationship} {rel['source_name']}"

                    finding = self.create_finding(
                        severity=severity,
                        category="semantic_appropriateness",
                        title=title,
                        description=f"LLM semantic analysis: {analysis.reasoning}",
                        confidence_score=confidence,
                        confidence_explanation=f"LLM confidence: {confidence_str} - {analysis.reasoning}",
                        suggested_action=suggested_action,
                        priority=2 if appropriateness == "INAPPROPRIATE" else 3,
                        evidence=[
                            f"Current relationship: {analysis.current_relationship}",
                            f"Source entity type: {analysis.source_entity_type}",
                            f"Target entity type: {analysis.target_entity_type}",
                            f"Suggested relationship: {analysis.suggested_relationship}",
                            f"Bidirectional assessment: {analysis.bidirectional_assessment}",
                            f"LLM reasoning: {analysis.reasoning}",
                        ],
                        affected_relationships=[rel_id],
                        metadata={
                            "semantic_analysis": True,
                            "appropriateness": appropriateness,
                            "suggested_relationship": analysis.suggested_relationship,
                            "suggested_reverse": analysis.suggested_reverse_relationship,
                            "source_entity_type": analysis.source_entity_type,
                            "target_entity_type": analysis.target_entity_type,
                        },
                    )
                    findings.append(finding)

        except Exception as e:
            error_type = type(e).__name__
            findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_semantic_analysis",
                    title="Failed to process LLM semantic analysis",
                    description="Could not process the structured LLM semantic analysis response",
                    confidence_score=0.9,
                    confidence_explanation="High confidence - processing error doesn't affect other validation",
                    suggested_action="Review LLM structured output or check data processing",
                    priority=4,
                    evidence=[
                        f"Processing error type: {error_type}",
                        f"Response data type: {type(response_data)}",
                    ],
                )
            )

        return findings

    async def _enhance_semantic_findings_with_llm(
        self, semantic_findings: list[ValidationFinding], relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Use LLM to enhance semantic consistency findings with detailed analysis."""
        enhanced_findings = []

        try:
            # Group findings by type for batch processing
            relates_to_missing = []
            mentions_complex = []
            formatting_issues = []

            for finding in semantic_findings:
                if "RELATES_TO lacks semantic clarity for LLM reasoning" in finding.title:
                    relates_to_missing.append(finding)
                elif "MENTIONS may have rich semantics suitable for RELATES_TO" in finding.title:
                    mentions_complex.append(finding)
                elif "Inconsistent semantic type formatting" in finding.title:
                    formatting_issues.append(finding)

            # Process each type with LLM
            if relates_to_missing:
                enhanced_findings.extend(
                    await self._analyze_missing_relates_to_semantics(
                        relates_to_missing, relationships
                    )
                )

            if mentions_complex:
                enhanced_findings.extend(
                    await self._analyze_complex_mentions(mentions_complex, relationships)
                )

            # Formatting issues don't need LLM analysis - they're deterministic

        except Exception as e:
            # If LLM enhancement fails, log but don't break validation
            error_type = type(e).__name__
            enhanced_findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_analysis",
                    title="LLM semantic enhancement failed",
                    description="Failed to enhance semantic findings with LLM analysis",
                    confidence_score=0.9,
                    confidence_explanation="High confidence - LLM enhancement failure doesn't affect rule-based findings",
                    suggested_action="Review semantic findings manually or check LLM configuration",
                    priority=4,
                    evidence=[f"Error type: {error_type}"],
                    metadata={"llm_enhancement_error": True},
                )
            )

        return enhanced_findings

    async def _analyze_missing_relates_to_semantics(
        self, findings: list[ValidationFinding], relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Use LLM to analyze RELATES_TO relationships missing semantic types."""
        enhanced_findings = []

        # Prepare relationship data for LLM analysis
        analysis_data = []
        for finding in findings:
            # Find the actual relationships mentioned in this finding
            for rel_id in finding.affected_relationships:
                rel = next((r for r in relationships if r["id"] == rel_id), None)
                if rel:
                    analysis_data.append(
                        {
                            "finding_id": finding.finding_id,
                            "source_name": rel.get("source_name", "Unknown"),
                            "target_name": rel.get("target_name", "Unknown"),
                            "properties": rel.get("props", {}),
                            "relationship_id": rel_id,
                        }
                    )

        if not analysis_data:
            return enhanced_findings

        # Create LLM prompt for analysis
        prompt = self._create_relates_to_analysis_prompt(analysis_data)

        try:
            # Run LLM analysis with structured output
            result = await self.agent.run(prompt, output_type=RelatesAnalysisResponse)

            # Process structured response and create enhanced findings
            enhanced_findings.extend(
                self._process_llm_relates_to_analysis(result.output, analysis_data)
            )

        except Exception as e:
            # Log LLM failure but continue
            error_type = type(e).__name__
            enhanced_findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_analysis",
                    title="LLM analysis failed for RELATES_TO semantics",
                    description="Could not analyze RELATES_TO semantic issues with the LLM",
                    confidence_score=0.8,
                    confidence_explanation="High confidence - LLM failure doesn't affect rule-based validation",
                    suggested_action="Review RELATES_TO relationships manually",
                    priority=4,
                    evidence=[f"LLM error type: {error_type}"],
                )
            )

        return enhanced_findings

    async def _analyze_complex_mentions(
        self, findings: list[ValidationFinding], relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Use LLM to analyze MENTIONS relationships with complex semantics."""
        enhanced_findings = []

        # Prepare data for LLM analysis
        analysis_data = []
        for finding in findings:
            for rel_id in finding.affected_relationships:
                rel = next((r for r in relationships if r["id"] == rel_id), None)
                if rel:
                    analysis_data.append(
                        {
                            "finding_id": finding.finding_id,
                            "source_name": rel.get("source_name", "Unknown"),
                            "target_name": rel.get("target_name", "Unknown"),
                            "semantic_type": self._extract_semantic_type(rel.get("props", {})),
                            "properties": rel.get("props", {}),
                            "relationship_id": rel_id,
                        }
                    )

        if not analysis_data:
            return enhanced_findings

        # Create LLM prompt
        prompt = self._create_mentions_analysis_prompt(analysis_data)

        try:
            result = await self.agent.run(prompt, output_type=MentionsAnalysisResponse)

            enhanced_findings.extend(
                self._process_llm_mentions_analysis(result.output, analysis_data)
            )

        except Exception as e:
            error_type = type(e).__name__
            enhanced_findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_analysis",
                    title="LLM analysis failed for MENTIONS semantics",
                    description="Could not analyze MENTIONS semantic complexity with the LLM",
                    confidence_score=0.8,
                    confidence_explanation="High confidence - LLM failure doesn't affect rule-based validation",
                    suggested_action="Review MENTIONS relationships manually",
                    priority=4,
                    evidence=[f"LLM error type: {error_type}"],
                )
            )

        return enhanced_findings

    def _create_relates_to_analysis_prompt(self, analysis_data: list[dict]) -> str:
        """Create LLM prompt for analyzing RELATES_TO relationships missing semantics."""
        relationships_text = ""
        for i, data in enumerate(analysis_data, 1):
            props_text = ", ".join([f"{k}: {v}" for k, v in data["properties"].items()])
            relationships_text += f"""
{i}. {data["source_name"]} → {data["target_name"]}
   Properties: {props_text or "None"}
   Relationship ID: {data["relationship_id"]}
"""

        return f"""Analyze these RELATES_TO relationships for hybrid GraphRAG semantic understanding.

You are helping optimize a hybrid GraphRAG system where LLMs need to understand relationship semantics for intelligent graph traversal and reasoning. The goal is semantic understanding, not strict formatting.

RELATES_TO relationships should have meaningful semantic types that help an LLM understand the nature of the relationship (like "allied_with", "opposed_to", "commands", "protects", "created_by", "worships", etc.).

RELATIONSHIPS TO ANALYZE:
{relationships_text}

For each relationship, focus on LLM understanding:
1. SEMANTIC_CLARITY: Will an LLM understand this relationship's meaning? (CLEAR, UNCLEAR, MISSING)
2. SUGGESTED_SEMANTIC_TYPE: What semantic type would best help an LLM understand this relationship?
3. GRAPHRAG_IMPACT: How important is this for graph reasoning? (HIGH, MEDIUM, LOW)
4. LLM_REASONING: How will this semantic type help an LLM traverse and reason about the graph?

Format your response as JSON:
{{
    "analyses": [
        {{
            "relationship_id": "...",
            "semantic_clarity": "CLEAR|UNCLEAR|MISSING",
            "suggested_semantic_type": "...",
            "graphrag_impact": "HIGH|MEDIUM|LOW",
            "llm_reasoning": "..."
        }}
    ]
}}"""

    def _create_mentions_analysis_prompt(self, analysis_data: list[dict]) -> str:
        """Create LLM prompt for analyzing MENTIONS with complex semantics."""
        relationships_text = ""
        for i, data in enumerate(analysis_data, 1):
            props_text = ", ".join([f"{k}: {v}" for k, v in data["properties"].items()])
            relationships_text += f"""
{i}. {data["source_name"]} → {data["target_name"]}
   Current semantic type: {data["semantic_type"]}
   Properties: {props_text or "None"}
   Relationship ID: {data["relationship_id"]}
"""

        return f"""Analyze these MENTIONS relationships for optimal hybrid GraphRAG performance.

In hybrid GraphRAG, we need clear distinction between:
- MENTIONS: Simple episode-to-entity links for document retrieval ("appears_in", "mentioned_in", "references")
- RELATES_TO: Rich semantic relationships for graph reasoning ("allied_with", "commands", "opposes")

This distinction helps the LLM know when to use document search vs. graph traversal for answering queries.

RELATIONSHIPS TO ANALYZE:
{relationships_text}

For each relationship, optimize for GraphRAG:
1. OPTIMAL_TYPE: Which type best serves hybrid GraphRAG? (MENTIONS, RELATES_TO)
2. GRAPHRAG_BENEFIT: How does this classification help the LLM? (CLEAR_SEPARATION, IMPROVED_REASONING, NEUTRAL)
3. SEMANTIC_RICHNESS: Does this semantic type add value for graph traversal? (HIGH_VALUE, SOME_VALUE, MINIMAL_VALUE)
4. LLM_STRATEGY: How should an LLM use this relationship type?

Format your response as JSON:
{{
    "analyses": [
        {{
            "relationship_id": "...",
            "optimal_type": "MENTIONS|RELATES_TO",
            "graphrag_benefit": "CLEAR_SEPARATION|IMPROVED_REASONING|NEUTRAL",
            "semantic_richness": "HIGH_VALUE|SOME_VALUE|MINIMAL_VALUE",
            "llm_strategy": "..."
        }}
    ]
}}"""

    def _parse_llm_relates_to_analysis(
        self, llm_response: str, analysis_data: list[dict]
    ) -> list[ValidationFinding]:
        """Parse LLM analysis of RELATES_TO relationships."""
        findings = []

        try:
            import json

            # Strip markdown code blocks if present
            clean_response = llm_response.strip()
            clean_response = clean_response.removeprefix("```json")  # Remove ```json
            clean_response = clean_response.removesuffix("```")  # Remove ```
            clean_response = clean_response.strip()

            response_data = json.loads(clean_response)

            for analysis in response_data.get("analyses", []):
                rel_id = analysis["relationship_id"]
                # Map semantic clarity to severity for GraphRAG optimization
                clarity_map = {
                    "CLEAR": ValidationSeverity.INFO,
                    "UNCLEAR": ValidationSeverity.WARNING,
                    "MISSING": ValidationSeverity.ERROR,
                }

                # Map GraphRAG impact to confidence score
                impact_map = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.5}

                severity = clarity_map.get(
                    analysis.get("semantic_clarity", "UNCLEAR"), ValidationSeverity.WARNING
                )
                confidence = impact_map.get(analysis.get("graphrag_impact", "MEDIUM"), 0.7)

                # Find original relationship data
                orig_data = next((d for d in analysis_data if d["relationship_id"] == rel_id), None)
                if not orig_data:
                    continue

                finding = self.create_finding(
                    severity=severity,
                    category="llm_graphrag_analysis",
                    title=f"GraphRAG Enhancement: RELATES_TO semantic clarity for {orig_data['source_name']} → {orig_data['target_name']}",
                    description=f"LLM analysis for hybrid GraphRAG optimization. {analysis['llm_reasoning']}",
                    confidence_score=confidence,
                    confidence_explanation=f"GraphRAG impact: {analysis.get('graphrag_impact', 'MEDIUM')} - {analysis['llm_reasoning']}",
                    suggested_action=f"Enhance semantic type for LLM understanding: '{analysis['suggested_semantic_type']}'",
                    priority=2 if severity == ValidationSeverity.ERROR else 3,
                    evidence=[
                        f"LLM suggested semantic type: {analysis['suggested_semantic_type']}",
                        f"Semantic clarity: {analysis.get('semantic_clarity', 'UNCLEAR')}",
                        f"GraphRAG impact: {analysis.get('graphrag_impact', 'MEDIUM')}",
                        f"LLM reasoning: {analysis['llm_reasoning']}",
                    ],
                    affected_relationships=[rel_id],
                    metadata={
                        "llm_analysis": True,
                        "suggested_semantic_type": analysis["suggested_semantic_type"],
                        "semantic_clarity": analysis.get("semantic_clarity", "UNCLEAR"),
                        "graphrag_impact": analysis.get("graphrag_impact", "MEDIUM"),
                    },
                )
                findings.append(finding)

        except Exception as e:
            error_type = type(e).__name__
            findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_analysis",
                    title="Failed to parse LLM RELATES_TO analysis",
                    description="Could not parse the LLM RELATES_TO semantic analysis response",
                    confidence_score=0.9,
                    confidence_explanation="High confidence - parsing error doesn't affect rule-based findings",
                    suggested_action="Review LLM response format or check JSON parsing",
                    priority=4,
                    evidence=[f"Parse error type: {error_type}"],
                )
            )

        return findings

    def _parse_llm_mentions_analysis(
        self, llm_response: str, analysis_data: list[dict]
    ) -> list[ValidationFinding]:
        """Parse LLM analysis of MENTIONS relationships."""
        findings = []

        try:
            import json

            # Strip markdown code blocks if present
            clean_response = llm_response.strip()
            clean_response = clean_response.removeprefix("```json")  # Remove ```json
            clean_response = clean_response.removesuffix("```")  # Remove ```
            clean_response = clean_response.strip()

            response_data = json.loads(clean_response)

            for analysis in response_data.get("analyses", []):
                rel_id = analysis["relationship_id"]
                # Map GraphRAG benefit to severity
                benefit_map = {
                    "CLEAR_SEPARATION": ValidationSeverity.INFO,
                    "IMPROVED_REASONING": ValidationSeverity.WARNING,
                    "NEUTRAL": ValidationSeverity.INFO,
                }

                # Map semantic richness to confidence
                richness_map = {"HIGH_VALUE": 0.9, "SOME_VALUE": 0.7, "MINIMAL_VALUE": 0.5}

                severity = benefit_map.get(
                    analysis.get("graphrag_benefit", "NEUTRAL"), ValidationSeverity.INFO
                )
                confidence = richness_map.get(analysis.get("semantic_richness", "SOME_VALUE"), 0.7)

                orig_data = next((d for d in analysis_data if d["relationship_id"] == rel_id), None)
                if not orig_data:
                    continue

                title = f"GraphRAG Optimization: MENTIONS classification for {orig_data['source_name']} → {orig_data['target_name']}"
                if analysis["optimal_type"] == "RELATES_TO":
                    title = f"GraphRAG Enhancement: Convert MENTIONS to RELATES_TO for {orig_data['source_name']} → {orig_data['target_name']}'"

                finding = self.create_finding(
                    severity=severity,
                    category="llm_graphrag_analysis",
                    title=title,
                    description=f"Hybrid GraphRAG optimization analysis. {analysis['llm_strategy']}",
                    confidence_score=confidence,
                    confidence_explanation=f"Semantic richness: {analysis.get('semantic_richness', 'SOME_VALUE')} - {analysis['llm_strategy']}",
                    suggested_action=(
                        f"Consider changing relationship type to {analysis['optimal_type']}"
                        if analysis["optimal_type"] != "MENTIONS"
                        else "Current MENTIONS classification is optimal for GraphRAG"
                    ),
                    priority=3 if analysis["optimal_type"] != "MENTIONS" else 4,
                    evidence=[
                        f"Current semantic type: {orig_data['semantic_type']}",
                        f"LLM recommended type: {analysis['optimal_type']}",
                        f"GraphRAG benefit: {analysis.get('graphrag_benefit', 'NEUTRAL')}",
                        f"Semantic richness: {analysis.get('semantic_richness', 'SOME_VALUE')}",
                        f"LLM strategy: {analysis['llm_strategy']}",
                    ],
                    affected_relationships=[rel_id],
                    metadata={
                        "llm_analysis": True,
                        "recommended_type": analysis["optimal_type"],
                        "graphrag_benefit": analysis.get("graphrag_benefit", "NEUTRAL"),
                        "semantic_richness": analysis.get("semantic_richness", "SOME_VALUE"),
                    },
                )
                findings.append(finding)

        except Exception as e:
            error_type = type(e).__name__
            findings.append(
                self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="llm_analysis",
                    title="Failed to parse LLM MENTIONS analysis",
                    description="Could not parse the LLM MENTIONS classification response",
                    confidence_score=0.9,
                    confidence_explanation="High confidence - parsing error doesn't affect rule-based findings",
                    suggested_action="Review LLM response format or check JSON parsing",
                    priority=4,
                    evidence=[f"Parse error type: {error_type}"],
                )
            )

        return findings

    async def _check_orphaned_entities(
        self, entities: list[dict], relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Check for entities with no relationships."""
        findings = []

        # Get all entity IDs that have relationships
        connected_entities = set()
        for rel in relationships:
            connected_entities.add(rel["source_id"])
            connected_entities.add(rel["target_id"])

        # Find orphaned entities
        for entity in entities:
            entity_id = entity["id"]
            if entity_id not in connected_entities:
                entity_name = entity.get("props", {}).get("name", "Unknown")

                finding = self.create_finding(
                    severity=ValidationSeverity.INFO,
                    category="entity_connectivity",
                    title="Orphaned entity with no relationships",
                    description=f"Entity '{entity_name}' has no incoming or outgoing relationships, which may indicate incomplete data extraction or isolated content.",
                    confidence_score=0.4,
                    confidence_explanation="Low confidence - some entities may legitimately have no relationships",
                    suggested_action="Review entity to determine if relationships are missing or if isolation is intentional",
                    priority=4,
                    evidence=[
                        f"Entity ID: {entity_id}",
                        f"Entity name: {entity_name}",
                        f"Labels: {entity.get('labels', [])}",
                    ],
                    affected_entities=[entity_id],
                )
                findings.append(finding)

        return findings

    async def _check_duplicate_relationships(
        self, relationships: list[dict]
    ) -> list[ValidationFinding]:
        """Check for duplicate relationships between same entities."""
        findings = []

        # Group relationships by source, target, and semantic type
        relationship_groups = {}

        for rel in relationships:
            source_id = rel["source_id"]
            target_id = rel["target_id"]
            rel_props = rel.get("props", {})
            semantic_type = self._extract_semantic_type(rel_props) or "unknown"

            group_key = (source_id, target_id, semantic_type.lower())

            if group_key not in relationship_groups:
                relationship_groups[group_key] = []

            relationship_groups[group_key].append(rel)

        # Find duplicates
        for group_key, group_rels in relationship_groups.items():
            if len(group_rels) > 1:
                source_name = group_rels[0].get("source_name", "Unknown")
                target_name = group_rels[0].get("target_name", "Unknown")
                semantic_type = group_key[2]

                finding = self.create_finding(
                    severity=ValidationSeverity.WARNING,
                    category="duplicate_relationships",
                    title=f"Duplicate relationships: {semantic_type}",
                    description=f"Found {len(group_rels)} duplicate '{semantic_type}' relationships between {source_name} and {target_name}.",
                    confidence_score=0.9,
                    confidence_explanation="Very high confidence - identical relationships between same entities are duplicates",
                    suggested_action=f"Remove {len(group_rels) - 1} duplicate relationships, keeping the most complete one",
                    priority=2,
                    evidence=[
                        f"Number of duplicates: {len(group_rels)}",
                        f"Between: {source_name} and {target_name}",
                        f"Semantic type: {semantic_type}",
                        f"Relationship IDs: {', '.join([rel['id'] for rel in group_rels])}",
                    ],
                    affected_relationships=[rel["id"] for rel in group_rels],
                )
                findings.append(finding)

        return findings

    def _extract_semantic_type(self, relationship_props: dict) -> str | None:
        """Extract semantic relationship type from properties."""

        # Check common property names for semantic type
        for prop_name in ["semantic_type", "relationship_type", "type", "kind", "nature"]:
            if prop_name in relationship_props:
                return str(relationship_props[prop_name])

        # Check if 'name' property contains semantic information (this is where Graphiti stores it)
        if "name" in relationship_props:
            # The name field contains the semantic type directly
            return str(relationship_props["name"])

        # Check for fact property that might contain semantic information
        if "fact" in relationship_props:
            fact = str(relationship_props["fact"])
            # Simple pattern matching for common relationship types
            fact_lower = fact.lower()
            if "allied with" in fact_lower or "alliance" in fact_lower:
                return "allied_with"
            elif "opposed to" in fact_lower or "enemy" in fact_lower:
                return "opposed_to"
            elif "commands" in fact_lower or "leads" in fact_lower:
                return "commands"
            elif "serves" in fact_lower or "follows" in fact_lower:
                return "serves_under"
            elif "protects" in fact_lower or "guards" in fact_lower:
                return "protects"

        return None
