"""
Base validator agent with audit trail system for Luminari Sage.

This module provides the foundation for all validation agents with comprehensive
audit trails, confidence scoring, and human review features. All changes made
by validation agents are labeled for easy human review.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from src.llm.pydantic_ai_factory import create_text_model


class ValidationSeverity(str, Enum):
    """Severity levels for validation findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationFinding(BaseModel):
    """A single validation finding with full audit trail."""

    # Core identification
    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = Field(..., description="ID of the agent that made this finding")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Finding details
    severity: ValidationSeverity = Field(..., description="Severity level of the finding")
    category: str = Field(
        ..., description="Category of validation (e.g., 'relationship_consistency')"
    )
    title: str = Field(..., description="Brief title of the finding")
    description: str = Field(..., description="Detailed description of the issue")

    # Evidence and context
    evidence: list[str] = Field(
        default_factory=list, description="Supporting evidence for this finding"
    )
    affected_entities: list[str] = Field(
        default_factory=list, description="Entity IDs affected by this finding"
    )
    affected_relationships: list[str] = Field(
        default_factory=list, description="Relationship IDs affected by this finding"
    )

    # Confidence and scoring
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in this finding (0.0-1.0)"
    )
    confidence_explanation: str = Field(..., description="Why this confidence score was assigned")

    # Suggested actions
    suggested_action: str = Field(..., description="What action should be taken")
    priority: int = Field(..., ge=1, le=5, description="Priority level (1=highest, 5=lowest)")

    # Human review tracking
    reviewed: bool = Field(default=False)
    reviewer: str | None = Field(None, description="Who reviewed this finding")
    review_timestamp: datetime | None = Field(None)
    review_action: str | None = Field(None, description="Action taken by reviewer")
    review_notes: str | None = Field(None)

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context data")


class ValidationReport(BaseModel):
    """Complete validation report with summary and findings."""

    # Report identification
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = Field(..., description="ID of the agent that generated this report")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Report scope
    validation_type: str = Field(..., description="Type of validation performed")
    scope_description: str = Field(..., description="What was validated")
    total_items_checked: int = Field(..., description="Total number of items validated")

    # Summary statistics
    findings_count: int = Field(..., description="Total number of findings")
    severity_counts: dict[str, int] = Field(default_factory=dict, description="Count by severity")
    category_counts: dict[str, int] = Field(default_factory=dict, description="Count by category")

    # All findings
    findings: list[ValidationFinding] = Field(default_factory=list)

    # Execution details
    execution_time_seconds: float = Field(..., description="How long the validation took")
    success: bool = Field(default=True, description="Whether validation completed successfully")
    error_message: str | None = Field(None, description="Error message if validation failed")

    # Additional metadata
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Additional metadata")

    def get_findings_by_severity(self, severity: ValidationSeverity) -> list[ValidationFinding]:
        """Get all findings of a specific severity level."""
        return [f for f in self.findings if f.severity == severity]

    def get_unreviewed_findings(self) -> list[ValidationFinding]:
        """Get all findings that haven't been reviewed by a human."""
        return [f for f in self.findings if not f.reviewed]

    def get_high_priority_findings(self) -> list[ValidationFinding]:
        """Get findings with priority 1 or 2."""
        return [f for f in self.findings if f.priority <= 2]

    def mark_finding_reviewed(self, finding_id: str, reviewer: str, action: str, notes: str = ""):
        """Mark a finding as reviewed by a human."""
        for finding in self.findings:
            if finding.finding_id == finding_id:
                finding.reviewed = True
                finding.reviewer = reviewer
                finding.review_timestamp = datetime.utcnow()
                finding.review_action = action
                finding.review_notes = notes
                break

    def to_markdown(self) -> str:
        """Generate a markdown report for human review."""
        lines = [
            f"# Validation Report: {self.validation_type}",
            f"**Generated by Agent:** `{self.agent_id}`  ",
            f"**Timestamp:** {self.timestamp.isoformat()}  ",
            f"**Scope:** {self.scope_description}  ",
            f"**Items Checked:** {self.total_items_checked}  ",
            f"**Execution Time:** {self.execution_time_seconds:.2f}s  ",
            "",
            "## Summary",
            f"- **Total Findings:** {self.findings_count}",
        ]

        # Add severity breakdown
        if self.severity_counts:
            lines.append("- **By Severity:**")
            for severity, count in self.severity_counts.items():
                lines.append(f"  - {severity.upper()}: {count}")

        # Add category breakdown
        if self.category_counts:
            lines.append("- **By Category:**")
            for category, count in self.category_counts.items():
                lines.append(f"  - {category}: {count}")

        lines.extend(["", "## Findings"])

        # Group findings by severity for better organization
        for severity in [
            ValidationSeverity.CRITICAL,
            ValidationSeverity.ERROR,
            ValidationSeverity.WARNING,
            ValidationSeverity.INFO,
        ]:
            severity_findings = self.get_findings_by_severity(severity)
            if not severity_findings:
                continue

            lines.append(f"### {severity.value.upper()} ({len(severity_findings)} findings)")

            for finding in severity_findings:
                lines.extend(
                    [
                        f"#### {finding.title}",
                        f"**Finding ID:** `{finding.finding_id}`  ",
                        f"**Agent:** `{finding.agent_id}`  ",
                        f"**Confidence:** {finding.confidence_score:.2f} - {finding.confidence_explanation}  ",
                        f"**Priority:** {finding.priority}/5  ",
                        f"**Category:** {finding.category}  ",
                        "",
                        finding.description,
                        "",
                        "**Suggested Action:**",
                        finding.suggested_action,
                    ]
                )

                if finding.evidence:
                    lines.append("**Evidence:**")
                    for evidence in finding.evidence:
                        lines.append(f"- {evidence}")
                    lines.append("")

                if finding.affected_entities:
                    lines.append(f"**Affected Entities:** {', '.join(finding.affected_entities)}  ")

                if finding.affected_relationships:
                    lines.append(
                        f"**Affected Relationships:** {', '.join(finding.affected_relationships)}  "
                    )

                # Review status
                if finding.reviewed:
                    lines.extend(
                        [
                            "",
                            "**✅ REVIEWED**",
                            f"- **Reviewer:** {finding.reviewer}",
                            f"- **Review Date:** {finding.review_timestamp.isoformat()}",
                            f"- **Action Taken:** {finding.review_action}",
                        ]
                    )
                    if finding.review_notes:
                        lines.append(f"- **Notes:** {finding.review_notes}")
                else:
                    lines.extend(["", "**⏳ PENDING HUMAN REVIEW**"])

                lines.append("---")

        return "\n".join(lines)


class BaseValidator:
    """
    Base class for all validation agents with comprehensive audit trails.

    All validation agents should inherit from this class to ensure consistent
    audit trails, confidence scoring, and human review capabilities.
    """

    def __init__(self, agent_id: str, openai_api_key: str | None = None):
        """Initialize the base validator."""
        self.agent_id = agent_id

        # Create the PydanticAI agent
        self.agent = Agent(
            create_text_model(
                "extraction",
                legacy_openai_api_key=openai_api_key,
                legacy_openai_model="gpt-4o-mini",
            ),
            system_prompt=self._get_system_prompt(),
        )

    def _get_system_prompt(self) -> str:
        """Get the system prompt for this validator agent."""
        return f"""You are a validation agent for the Luminari Sage knowledge graph system.

AGENT IDENTIFICATION: {self.agent_id}

Your role is to analyze knowledge graph data and identify potential issues, inconsistencies,
or improvements. You have access to entity and relationship data from a Neo4j graph database
containing fantasy lore information.

CRITICAL REQUIREMENTS:
1. Every finding MUST include your agent ID: {self.agent_id}
2. Every finding MUST include a confidence score (0.0-1.0) with explanation
3. Every finding MUST be labeled for human review
4. You CANNOT make automatic changes - only suggest actions
5. Provide specific evidence for all findings
6. Be thorough but not overly verbose

CONFIDENCE SCORING GUIDELINES:
- 0.9-1.0: Very high confidence (clear logical contradiction, missing required data)
- 0.7-0.8: High confidence (strong pattern match, multiple supporting evidence)
- 0.5-0.6: Medium confidence (possible issue, limited evidence)
- 0.3-0.4: Low confidence (speculation, unclear patterns)
- 0.1-0.2: Very low confidence (weak signals, requires human judgment)

Focus on actionable findings that improve data quality and consistency."""

    def create_finding(
        self,
        severity: ValidationSeverity,
        category: str,
        title: str,
        description: str,
        confidence_score: float,
        confidence_explanation: str,
        suggested_action: str,
        priority: int = 3,
        evidence: list[str] | None = None,
        affected_entities: list[str] | None = None,
        affected_relationships: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ValidationFinding:
        """Create a new validation finding with full audit trail."""
        return ValidationFinding(
            agent_id=self.agent_id,
            severity=severity,
            category=category,
            title=title,
            description=description,
            confidence_score=confidence_score,
            confidence_explanation=confidence_explanation,
            suggested_action=suggested_action,
            priority=priority,
            evidence=evidence or [],
            affected_entities=affected_entities or [],
            affected_relationships=affected_relationships or [],
            metadata=metadata or {},
        )

    def create_report(
        self,
        validation_type: str,
        scope_description: str,
        total_items_checked: int,
        findings: list[ValidationFinding],
        execution_time_seconds: float,
        success: bool = True,
        error_message: str | None = None,
    ) -> ValidationReport:
        """Create a validation report with summary statistics."""

        # Calculate summary statistics
        severity_counts = {}
        category_counts = {}

        for finding in findings:
            # Count by severity
            severity_key = finding.severity.value
            severity_counts[severity_key] = severity_counts.get(severity_key, 0) + 1

            # Count by category
            category_counts[finding.category] = category_counts.get(finding.category, 0) + 1

        return ValidationReport(
            agent_id=self.agent_id,
            validation_type=validation_type,
            scope_description=scope_description,
            total_items_checked=total_items_checked,
            findings_count=len(findings),
            severity_counts=severity_counts,
            category_counts=category_counts,
            findings=findings,
            execution_time_seconds=execution_time_seconds,
            success=success,
            error_message=error_message,
        )

    async def validate(self, *args, **kwargs) -> ValidationReport:
        """
        Perform validation and return a report.

        This method should be overridden by subclasses to implement
        specific validation logic.
        """
        raise NotImplementedError("Subclasses must implement the validate method")
