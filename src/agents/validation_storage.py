"""
Validation history storage service for Luminari Sage.

This module handles storing and retrieving validation reports and findings
in PostgreSQL for audit trails and human review.
"""

import json
from typing import Any

from ..db import get_postgres_db
from .base_validator import ValidationReport


class ValidationStorageService:
    """Service for storing and retrieving validation history in PostgreSQL."""

    @staticmethod
    async def store_report(report: ValidationReport) -> str:
        """
        Store a validation report and its findings in PostgreSQL.

        Args:
            report: The validation report to store

        Returns:
            The database UUID of the stored report
        """
        postgres_db = await get_postgres_db()

        # Insert the main report
        report_query = """
            INSERT INTO validation_reports (
                report_id, agent_id, created_at, validation_type, scope_description,
                total_items_checked, findings_count, severity_counts, category_counts,
                execution_time_seconds, success, error_message, markdown_report
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            ) RETURNING id
        """

        report_row = await postgres_db.fetchrow(
            report_query,
            report.report_id,
            report.agent_id,
            report.timestamp,
            report.validation_type,
            report.scope_description,
            report.total_items_checked,
            report.findings_count,
            json.dumps(report.severity_counts),
            json.dumps(report.category_counts),
            report.execution_time_seconds,
            report.success,
            report.error_message,
            report.to_markdown(),
        )

        db_report_id = report_row["id"]

        # Insert all findings
        if report.findings:
            finding_query = """
                INSERT INTO validation_findings (
                    finding_id, report_id, agent_id, created_at, severity, category,
                    title, description, confidence_score, confidence_explanation,
                    evidence, suggested_action, priority, affected_entities,
                    affected_relationships, reviewed, reviewer, review_timestamp,
                    review_action, review_notes
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
                )
            """

            for finding in report.findings:
                await postgres_db.execute(
                    finding_query,
                    finding.finding_id,
                    db_report_id,
                    finding.agent_id,
                    finding.timestamp,
                    finding.severity.value,
                    finding.category,
                    finding.title,
                    finding.description,
                    finding.confidence_score,
                    finding.confidence_explanation,
                    json.dumps(finding.evidence),
                    finding.suggested_action,
                    finding.priority,
                    json.dumps(finding.affected_entities),
                    json.dumps(finding.affected_relationships),
                    finding.reviewed,
                    finding.reviewer,
                    finding.review_timestamp,
                    finding.review_action,
                    finding.review_notes,
                )

        return str(db_report_id)

    @staticmethod
    async def get_report(report_id: str) -> dict[str, Any] | None:
        """
        Retrieve a validation report by ID.

        Args:
            report_id: The report ID to retrieve

        Returns:
            Report data as dictionary or None if not found
        """
        postgres_db = await get_postgres_db()

        # Get the main report
        report_query = """
            SELECT * FROM validation_reports
            WHERE report_id = $1
        """

        report_row = await postgres_db.fetchrow(report_query, report_id)
        if not report_row:
            return None

        # Get all findings for this report
        findings_query = """
            SELECT * FROM validation_findings
            WHERE report_id = $1
            ORDER BY priority ASC, created_at ASC
        """

        finding_rows = await postgres_db.fetch(findings_query, report_row["id"])

        # Convert to dictionary format
        report_data = dict(report_row)
        report_data["severity_counts"] = json.loads(report_data["severity_counts"])
        report_data["category_counts"] = json.loads(report_data["category_counts"])

        findings_data = []
        for finding_row in finding_rows:
            finding_data = dict(finding_row)
            finding_data["evidence"] = json.loads(finding_data["evidence"])
            finding_data["affected_entities"] = json.loads(finding_data["affected_entities"])
            finding_data["affected_relationships"] = json.loads(
                finding_data["affected_relationships"]
            )
            findings_data.append(finding_data)

        report_data["findings"] = findings_data
        return report_data

    @staticmethod
    async def list_reports(
        agent_id: str | None = None,
        validation_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List validation reports with optional filtering.

        Args:
            agent_id: Filter by agent ID
            validation_type: Filter by validation type
            limit: Maximum number of reports to return
            offset: Number of reports to skip

        Returns:
            List of report summaries
        """
        postgres_db = await get_postgres_db()

        # Build query with optional filters
        where_clauses = []
        params = []
        param_count = 0

        if agent_id:
            param_count += 1
            where_clauses.append(f"agent_id = ${param_count}")
            params.append(agent_id)

        if validation_type:
            param_count += 1
            where_clauses.append(f"validation_type = ${param_count}")
            params.append(validation_type)

        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        param_count += 1
        limit_clause = f"LIMIT ${param_count}"
        params.append(limit)

        param_count += 1
        offset_clause = f"OFFSET ${param_count}"
        params.append(offset)

        query = f"""
            SELECT
                report_id, agent_id, created_at, validation_type, scope_description,
                total_items_checked, findings_count, severity_counts, category_counts,
                execution_time_seconds, success, error_message
            FROM validation_reports
            {where_clause}
            ORDER BY created_at DESC
            {limit_clause} {offset_clause}
        """

        rows = await postgres_db.fetch(query, *params)

        results = []
        for row in rows:
            row_data = dict(row)
            row_data["severity_counts"] = json.loads(row_data["severity_counts"])
            row_data["category_counts"] = json.loads(row_data["category_counts"])
            results.append(row_data)

        return results

    @staticmethod
    async def mark_finding_reviewed(
        finding_id: str, reviewer: str, action: str, notes: str = ""
    ) -> bool:
        """
        Mark a finding as reviewed by a human.

        Args:
            finding_id: The finding ID to mark as reviewed
            reviewer: Name/ID of the reviewer
            action: Action taken by the reviewer
            notes: Optional review notes

        Returns:
            True if the finding was found and updated
        """
        postgres_db = await get_postgres_db()

        query = """
            UPDATE validation_findings
            SET
                reviewed = TRUE,
                reviewer = $2,
                review_timestamp = NOW(),
                review_action = $3,
                review_notes = $4
            WHERE finding_id = $1
        """

        result = await postgres_db.execute(query, finding_id, reviewer, action, notes)
        return result != "UPDATE 0"  # Returns True if at least one row was updated

    @staticmethod
    async def get_unreviewed_findings(
        severity: str | None = None,
        category: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get unreviewed findings with optional filtering.

        Args:
            severity: Filter by severity level
            category: Filter by category
            agent_id: Filter by agent ID
            limit: Maximum number of findings to return

        Returns:
            List of unreviewed findings
        """
        postgres_db = await get_postgres_db()

        # Build query with optional filters
        where_clauses = ["reviewed = FALSE"]
        params = []
        param_count = 0

        if severity:
            param_count += 1
            where_clauses.append(f"severity = ${param_count}")
            params.append(severity)

        if category:
            param_count += 1
            where_clauses.append(f"category = ${param_count}")
            params.append(category)

        if agent_id:
            param_count += 1
            where_clauses.append(f"agent_id = ${param_count}")
            params.append(agent_id)

        where_clause = "WHERE " + " AND ".join(where_clauses)

        param_count += 1
        limit_clause = f"LIMIT ${param_count}"
        params.append(limit)

        query = f"""
            SELECT f.*, r.validation_type, r.scope_description
            FROM validation_findings f
            JOIN validation_reports r ON f.report_id = r.id
            {where_clause}
            ORDER BY f.priority ASC, f.created_at DESC
            {limit_clause}
        """

        rows = await postgres_db.fetch(query, *params)

        results = []
        for row in rows:
            row_data = dict(row)
            row_data["evidence"] = json.loads(row_data["evidence"])
            row_data["affected_entities"] = json.loads(row_data["affected_entities"])
            row_data["affected_relationships"] = json.loads(row_data["affected_relationships"])
            results.append(row_data)

        return results

    @staticmethod
    async def get_statistics() -> dict[str, Any]:
        """
        Get validation statistics summary.

        Returns:
            Dictionary with validation statistics
        """
        postgres_db = await get_postgres_db()

        # Get report statistics
        report_stats_query = """
            SELECT
                COUNT(*) as total_reports,
                COUNT(CASE WHEN success THEN 1 END) as successful_reports,
                COUNT(DISTINCT agent_id) as unique_agents,
                COUNT(DISTINCT validation_type) as validation_types,
                AVG(execution_time_seconds) as avg_execution_time,
                MAX(created_at) as last_report_time
            FROM validation_reports
        """

        report_stats = await postgres_db.fetchrow(report_stats_query)

        # Get finding statistics
        finding_stats_query = """
            SELECT
                COUNT(*) as total_findings,
                COUNT(CASE WHEN reviewed THEN 1 END) as reviewed_findings,
                COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_findings,
                COUNT(CASE WHEN severity = 'error' THEN 1 END) as error_findings,
                COUNT(CASE WHEN severity = 'warning' THEN 1 END) as warning_findings,
                COUNT(CASE WHEN severity = 'info' THEN 1 END) as info_findings,
                COUNT(DISTINCT category) as unique_categories,
                AVG(confidence_score) as avg_confidence_score
            FROM validation_findings
        """

        finding_stats = await postgres_db.fetchrow(finding_stats_query)

        # Get top categories
        category_stats_query = """
            SELECT category, COUNT(*) as count
            FROM validation_findings
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """

        category_stats = await postgres_db.fetch(category_stats_query)

        return {
            "reports": dict(report_stats),
            "findings": dict(finding_stats),
            "top_categories": [dict(row) for row in category_stats],
        }
