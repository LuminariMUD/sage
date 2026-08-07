"""Pure, content-free operational readiness and alert reporting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class OperationalThresholds:
    """Explicit provisional alert thresholds, separate from release quality gates."""

    retry_storm_min_attempts: int = 5
    retry_storm_percent: float = 25.0
    provider_failure_min_calls: int = 5
    provider_failure_percent: float = 25.0

    def __post_init__(self) -> None:
        for value, label in (
            (self.retry_storm_min_attempts, "Retry-storm minimum attempts"),
            (self.provider_failure_min_calls, "Provider-failure minimum calls"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{label} must be a positive integer")
        for value, label in (
            (self.retry_storm_percent, "Retry-storm percentage"),
            (self.provider_failure_percent, "Provider-failure percentage"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{label} must be numeric")
            if not 0 < float(value) <= 100:
                raise ValueError(f"{label} must be greater than 0 and at most 100")

    def as_dict(self) -> dict[str, int | float]:
        return {
            "retry_storm_min_attempts": self.retry_storm_min_attempts,
            "retry_storm_percent": float(self.retry_storm_percent),
            "provider_failure_min_calls": self.provider_failure_min_calls,
            "provider_failure_percent": float(self.provider_failure_percent),
        }


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 3)


def summarize_graph_audit(report: Mapping[str, Any]) -> dict[str, Any]:
    """Strip per-episode drift records while preserving actionable aggregate counts."""
    counts = report.get("counts")
    drift = report.get("drift")
    coverage = report.get("metadata_coverage")
    drift_counts: dict[str, int] = {}
    if isinstance(drift, Mapping):
        for name, findings in drift.items():
            if isinstance(findings, bool):
                continue
            if isinstance(findings, int):
                drift_counts[str(name)] = max(0, findings)
            elif isinstance(findings, list):
                drift_counts[str(name)] = len(findings)

    safe_counts: dict[str, Any] = {}
    if isinstance(counts, Mapping):
        for name, value in counts.items():
            if name == "lifecycle" and isinstance(value, Mapping):
                safe_counts[name] = {str(state): _count(count) for state, count in value.items()}
            elif isinstance(value, int) and not isinstance(value, bool):
                safe_counts[str(name)] = max(0, value)

    safe_coverage = {}
    if isinstance(coverage, Mapping):
        safe_coverage = {
            str(name): _count(value)
            for name, value in coverage.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }

    return {
        "schema_version": 1,
        "status": str(report.get("status") or "incomplete"),
        "state_source": report.get("state_source"),
        "counts": safe_counts,
        "metadata_coverage": safe_coverage,
        "drift_counts": drift_counts,
    }


def summarize_embedding_preflight(report: Mapping[str, Any]) -> dict[str, Any]:
    """Keep profile identity, physical counts, and finding codes without verbose detail."""
    safe_spaces = []
    spaces = report.get("spaces")
    if isinstance(spaces, list):
        for raw_space in spaces:
            if not isinstance(raw_space, Mapping):
                continue
            configured = raw_space.get("configured_profile")
            metadata = raw_space.get("metadata")
            physical = raw_space.get("physical")
            index = physical.get("index") if isinstance(physical, Mapping) else None
            findings = raw_space.get("findings")
            safe_spaces.append(
                {
                    "semantic_index": raw_space.get("semantic_index"),
                    "physical_space": raw_space.get("physical_space"),
                    "status": raw_space.get("status"),
                    "ready": raw_space.get("ready") is True,
                    "configured_profile_fingerprint": (
                        configured.get("fingerprint") if isinstance(configured, Mapping) else None
                    ),
                    "stored_profile_fingerprint": (
                        metadata.get("profile_fingerprint")
                        if isinstance(metadata, Mapping)
                        else None
                    ),
                    "dimensions": (
                        physical.get("dimensions") if isinstance(physical, Mapping) else None
                    ),
                    "total_rows": (
                        physical.get("total_rows") if isinstance(physical, Mapping) else None
                    ),
                    "embedded_rows": (
                        physical.get("embedded_rows") if isinstance(physical, Mapping) else None
                    ),
                    "index_ready": (
                        index.get("ready") is True if isinstance(index, Mapping) else False
                    ),
                    "findings": (
                        [
                            {
                                "code": finding.get("code"),
                                "severity": finding.get("severity"),
                            }
                            for finding in findings
                            if isinstance(finding, Mapping)
                        ]
                        if isinstance(findings, list)
                        else []
                    ),
                }
            )
    return {
        "schema_version": 1,
        "status": str(report.get("status") or "incomplete"),
        "scope": report.get("scope"),
        "spaces": safe_spaces,
    }


def summarize_relationship_quality(report: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve only the versioned, content-free relationship metrics contract."""
    run = report.get("run")
    evidence = report.get("evidence")
    vocabulary = report.get("vocabulary")
    return {
        "schema_version": 1,
        "status": str(report.get("status") or "unavailable"),
        "reason": report.get("reason"),
        "run": (
            {
                key: run.get(key)
                for key in (
                    "id",
                    "state",
                    "sync_profile_fingerprint",
                    "started_at",
                    "stopped_at",
                )
            }
            if isinstance(run, Mapping)
            else None
        ),
        "evidence": (
            {
                key: evidence.get(key)
                for key in (
                    "status",
                    "successful_attempts",
                    "reported_attempts",
                    "missing_attempts",
                    "coverage_percent",
                )
            }
            if isinstance(evidence, Mapping)
            else {}
        ),
        "vocabulary": (
            {
                "fingerprints": list(vocabulary.get("fingerprints") or []),
                "mixed": vocabulary.get("mixed") is True,
            }
            if isinstance(vocabulary, Mapping)
            else {"fingerprints": [], "mixed": False}
        ),
        "relationships": (
            dict(report["relationships"])
            if isinstance(report.get("relationships"), Mapping)
            else {}
        ),
        "rates_percent": (
            dict(report["rates_percent"])
            if isinstance(report.get("rates_percent"), Mapping)
            else {}
        ),
        "rejection_reasons": (
            dict(report["rejection_reasons"])
            if isinstance(report.get("rejection_reasons"), Mapping)
            else {}
        ),
    }


def _safe_run_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    run = summary.get("run")
    if not isinstance(run, Mapping):
        return {
            "schema_version": 1,
            "status": str(summary.get("status") or "no_runs"),
            "run": None,
        }
    safe_run = {
        key: run.get(key)
        for key in (
            "id",
            "state",
            "sync_profile_fingerprint",
            "started_at",
            "heartbeat_at",
            "stopped_at",
            "last_failure_class",
            "last_failure_code",
        )
    }
    return {
        "schema_version": 1,
        "status": str(summary.get("status") or "available"),
        "run": safe_run,
        "progress": summary.get("progress") if isinstance(summary.get("progress"), Mapping) else {},
        "attempts": summary.get("attempts") if isinstance(summary.get("attempts"), Mapping) else {},
        "provider_calls": (
            summary.get("provider_calls")
            if isinstance(summary.get("provider_calls"), Mapping)
            else {}
        ),
    }


def _safe_sync_status(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    counts = snapshot.get("counts")
    ledger = snapshot.get("ledger")
    active_run = snapshot.get("active_run")
    return {
        "queue": {
            "counts": (
                {
                    str(state): _count(count)
                    for state, count in counts.items()
                    if isinstance(state, str)
                }
                if isinstance(counts, Mapping)
                else {}
            ),
            "total": _count(snapshot.get("total")),
            "eligible": _count(snapshot.get("eligible")),
            "expired_leases": _count(snapshot.get("expired_leases")),
            "job_attempts": _count(snapshot.get("job_attempts")),
        },
        "ledger": (
            {str(name): _count(value) for name, value in ledger.items() if isinstance(name, str)}
            if isinstance(ledger, Mapping)
            else {}
        ),
        "active_run": (
            {
                key: active_run.get(key)
                for key in (
                    "id",
                    "state",
                    "sync_profile_fingerprint",
                    "started_at",
                    "updated_at",
                    "heartbeat_at",
                    "last_failure_class",
                    "last_failure_code",
                )
            }
            if isinstance(active_run, Mapping)
            else None
        ),
    }


def _baseline_quarantined(report: Mapping[str, Any] | None) -> int | None:
    if report is None:
        return None
    graph_sync = report.get("graph_sync")
    queue = graph_sync.get("queue") if isinstance(graph_sync, Mapping) else None
    counts = queue.get("counts") if isinstance(queue, Mapping) else None
    value = counts.get("quarantined") if isinstance(counts, Mapping) else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def build_operational_readiness(
    *,
    configuration: Mapping[str, Any],
    configured_sync_profile: str,
    sync_snapshot: Mapping[str, Any],
    run_summary: Mapping[str, Any],
    relationship_quality: Mapping[str, Any],
    graph_audit: Mapping[str, Any],
    embedding_preflight: Mapping[str, Any],
    thresholds: OperationalThresholds | None = None,
    baseline_report: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one bounded report and deterministic alerts from read-only components."""
    if not configured_sync_profile:
        raise ValueError("Configured sync profile is required")
    thresholds = thresholds or OperationalThresholds()
    safe_sync = _safe_sync_status(sync_snapshot)
    safe_run = _safe_run_summary(run_summary)
    safe_audit = summarize_graph_audit(graph_audit)
    safe_embedding = summarize_embedding_preflight(embedding_preflight)
    safe_quality = summarize_relationship_quality(relationship_quality)
    alerts: list[dict[str, Any]] = []

    def add_alert(
        code: str,
        *,
        severity: str,
        source: str,
        observed: Any,
        threshold: Any,
        message: str,
    ) -> None:
        alerts.append(
            {
                "code": code,
                "severity": severity,
                "source": source,
                "observed": observed,
                "threshold": threshold,
                "message": message,
            }
        )

    queue = safe_sync["queue"]
    queue_counts = queue["counts"]
    quarantined = _count(queue_counts.get("quarantined"))
    expired_leases = _count(queue.get("expired_leases"))
    if quarantined:
        add_alert(
            "quarantined_jobs_present",
            severity="critical",
            source="graph_sync",
            observed=quarantined,
            threshold=0,
            message="Quarantined graph jobs require operator review",
        )
    if expired_leases:
        add_alert(
            "expired_leases_present",
            severity="critical",
            source="graph_sync",
            observed=expired_leases,
            threshold=0,
            message="Expired graph leases require recovery or investigation",
        )

    baseline_quarantined = _baseline_quarantined(baseline_report)
    if baseline_quarantined is not None and quarantined > baseline_quarantined:
        add_alert(
            "quarantined_jobs_growing",
            severity="critical",
            source="graph_sync",
            observed={"baseline": baseline_quarantined, "current": quarantined},
            threshold="no_growth",
            message="Quarantined graph jobs increased since the baseline report",
        )

    active_run = safe_sync.get("active_run")
    if isinstance(active_run, Mapping):
        if active_run.get("sync_profile_fingerprint") != configured_sync_profile:
            add_alert(
                "active_sync_profile_mismatch",
                severity="critical",
                source="graph_sync",
                observed=active_run.get("sync_profile_fingerprint"),
                threshold=configured_sync_profile,
                message="The active run does not use the configured sync profile",
            )
        if active_run.get("state") == "paused_systemic":
            add_alert(
                "run_paused_systemic",
                severity="critical",
                source="graph_sync",
                observed="paused_systemic",
                threshold="running_or_idle",
                message="The graph run paused after a systemic failure",
            )

    attempts = safe_run.get("attempts")
    if isinstance(attempts, Mapping):
        completed_attempts = _count(attempts.get("completed_attempts"))
        outcomes = attempts.get("outcomes")
        retrying = 0
        if isinstance(outcomes, Mapping):
            retrying = _count(outcomes.get("retry_wait")) + _count(outcomes.get("quarantined"))
        retry_percent = _percentage(retrying, completed_attempts)
        if (
            completed_attempts >= thresholds.retry_storm_min_attempts
            and retry_percent is not None
            and retry_percent >= thresholds.retry_storm_percent
        ):
            add_alert(
                "retry_storm",
                severity="warning",
                source="graph_sync",
                observed={"attempts": completed_attempts, "percent": retry_percent},
                threshold={
                    "minimum_attempts": thresholds.retry_storm_min_attempts,
                    "percent": float(thresholds.retry_storm_percent),
                },
                message="Graph retries exceed the provisional operational threshold",
            )

    provider_calls = safe_run.get("provider_calls")
    candidates = provider_calls.get("candidates") if isinstance(provider_calls, Mapping) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            completed = _count(candidate.get("completed"))
            outcomes = candidate.get("outcomes")
            failures = _count(outcomes.get("failure")) if isinstance(outcomes, Mapping) else 0
            failure_percent = _percentage(failures, completed)
            if (
                completed >= thresholds.provider_failure_min_calls
                and failure_percent is not None
                and failure_percent >= thresholds.provider_failure_percent
            ):
                add_alert(
                    "sustained_provider_failure",
                    severity="warning",
                    source="provider_candidate",
                    observed={
                        "candidate_fingerprint": candidate.get("candidate_fingerprint"),
                        "completed_calls": completed,
                        "failure_percent": failure_percent,
                    },
                    threshold={
                        "minimum_calls": thresholds.provider_failure_min_calls,
                        "percent": float(thresholds.provider_failure_percent),
                    },
                    message="A provider candidate exceeds the provisional failure threshold",
                )

    quality_status = safe_quality["status"]
    if quality_status == "available":
        evidence = safe_quality["evidence"]
        vocabulary = safe_quality["vocabulary"]
        missing_attempts = (
            _count(evidence.get("missing_attempts")) if isinstance(evidence, Mapping) else 0
        )
        if missing_attempts:
            add_alert(
                "relationship_quality_evidence_incomplete",
                severity="critical",
                source="relationship_quality",
                observed=missing_attempts,
                threshold=0,
                message="Successful attempts are missing relationship-quality evidence",
            )
        if isinstance(vocabulary, Mapping) and vocabulary.get("mixed") is True:
            add_alert(
                "relationship_vocabulary_mixed",
                severity="critical",
                source="relationship_quality",
                observed=True,
                threshold=False,
                message="A run contains more than one relationship vocabulary fingerprint",
            )
    elif quality_status != "no_runs":
        add_alert(
            "relationship_quality_unavailable",
            severity="critical",
            source="relationship_quality",
            observed=quality_status,
            threshold="available_or_no_runs",
            message="Relationship-quality evidence cannot be inspected",
        )

    audit_status = safe_audit["status"]
    audit_drift_count = _count(safe_audit["counts"].get("drift_findings"))
    if audit_status == "drift" or audit_drift_count:
        add_alert(
            "graph_audit_drift",
            severity="critical",
            source="graph_audit",
            observed=audit_drift_count,
            threshold=0,
            message="Cross-store graph reconciliation found drift",
        )
    elif audit_status != "clean":
        add_alert(
            "graph_audit_incomplete",
            severity="critical",
            source="graph_audit",
            observed=audit_status,
            threshold="clean",
            message="Cross-store graph reconciliation did not complete cleanly",
        )

    profile_drift_names = (
        "job_sync_profile_mismatches",
        "sync_profile_mismatches",
        "embedding_profile_mismatches",
    )
    profile_drift = sum(
        _count(safe_audit["drift_counts"].get(name)) for name in profile_drift_names
    )
    if profile_drift:
        add_alert(
            "graph_profile_mismatch",
            severity="critical",
            source="graph_audit",
            observed=profile_drift,
            threshold=0,
            message="Graph records do not match the configured profile identities",
        )

    mismatch_codes = sorted(
        {
            str(finding["code"])
            for space in safe_embedding["spaces"]
            for finding in space["findings"]
            if isinstance(finding.get("code"), str)
            and ("profile" in str(finding["code"]) or "dimension_mismatch" in str(finding["code"]))
        }
    )
    if mismatch_codes:
        add_alert(
            "embedding_profile_mismatch",
            severity="critical",
            source="embedding_preflight",
            observed=mismatch_codes,
            threshold=[],
            message="The active embedding space does not match its configured profile",
        )
    if safe_embedding["status"] != "ready":
        add_alert(
            "embedding_preflight_blocked",
            severity="critical",
            source="embedding_preflight",
            observed=safe_embedding["status"],
            threshold="ready",
            message="Embedding preflight is not ready",
        )

    severity_order = {"critical": 0, "warning": 1}
    alerts.sort(key=lambda alert: (severity_order[alert["severity"]], alert["code"]))
    critical_count = sum(alert["severity"] == "critical" for alert in alerts)
    warning_count = sum(alert["severity"] == "warning" for alert in alerts)
    if critical_count:
        status = "blocked"
    elif warning_count:
        status = "degraded"
    else:
        status = "ready"

    timestamp = generated_at or datetime.now(UTC)
    return {
        "schema_version": 1,
        "generated_at": timestamp.isoformat(),
        "status": status,
        "ready": status == "ready",
        "configuration": dict(configuration),
        "thresholds": thresholds.as_dict(),
        "baseline": {
            "provided": baseline_report is not None,
            "quarantined_jobs": baseline_quarantined,
        },
        "graph_sync": {
            **safe_sync,
            "latest_run": safe_run,
            "relationship_quality": safe_quality,
        },
        "graph_audit": safe_audit,
        "embedding_preflight": safe_embedding,
        "alerts": {
            "critical": critical_count,
            "warning": warning_count,
            "items": alerts,
        },
    }
