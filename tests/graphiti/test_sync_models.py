"""Unit tests for durable Graphiti lifecycle contracts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.graphiti.sync_models import (
    FailureClass,
    FailureDisposition,
    FailureRecord,
    GraphSyncPolicy,
    ProviderCallOutcome,
    ProviderCallRecord,
    deterministic_retry_delay,
    sanitize_summary,
)


def test_deterministic_backoff_is_stable_bounded_and_attempt_sensitive():
    episode_id = UUID("11111111-1111-1111-1111-111111111111")

    first = deterministic_retry_delay(episode_id, 1, base_seconds=60, maximum_seconds=3600)
    repeated = deterministic_retry_delay(episode_id, 1, base_seconds=60, maximum_seconds=3600)
    third = deterministic_retry_delay(episode_id, 3, base_seconds=60, maximum_seconds=3600)

    assert first == repeated
    assert 48 <= first <= 72
    assert 192 <= third <= 288
    assert deterministic_retry_delay(episode_id, 50, base_seconds=60, maximum_seconds=3600) <= 3600


@pytest.mark.parametrize(
    "policy",
    [
        GraphSyncPolicy(),
        GraphSyncPolicy(
            lease_seconds=30,
            max_job_attempts=1,
            retry_base_seconds=1,
            retry_max_seconds=1,
            max_provider_calls=1,
        ),
    ],
)
def test_policy_accepts_valid_bounds(policy):
    assert policy.max_job_attempts >= 1


def test_policy_rejects_unbounded_values():
    with pytest.raises(ValueError, match="Lease"):
        GraphSyncPolicy(lease_seconds=1)
    with pytest.raises(ValueError, match="provider calls"):
        GraphSyncPolicy(max_provider_calls=101)


def test_failure_record_redacts_and_bounds_operator_summary():
    secret = "sk_test_abcdefghijklmnopqrstuvwxyz"
    record = FailureRecord.build(
        failure_class=FailureClass.AUTHENTICATION,
        code="provider_authentication",
        summary=f"Authorization: Bearer {secret}\n" + ("x" * 600),
        disposition=FailureDisposition.PAUSE_SYSTEMIC,
    )

    assert secret not in record.summary
    assert "<redacted>" in record.summary
    assert "\n" not in record.summary
    assert len(record.summary) == 512
    assert sanitize_summary("\x00\x01") == "No sanitized detail available"


def test_failure_record_constructor_cannot_bypass_redaction():
    secret = "sk_test_abcdefghijklmnopqrstuvwxyz"

    record = FailureRecord(
        failure_class=FailureClass.CONFIGURATION,
        code="invalid_configuration",
        summary=f"api_key={secret}",
        disposition=FailureDisposition.PAUSE_SYSTEMIC,
    )

    assert secret not in record.summary
    assert "<redacted>" in record.summary


def test_provider_call_requires_failure_taxonomy_and_valid_timing():
    started = datetime.now(UTC)
    failed = ProviderCallRecord(
        logical_model_attempt=1,
        transport_attempt=1,
        provider="ollama",
        model="qwen2.5:3b",
        candidate_fingerprint="candidate:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        started_at=started,
        completed_at=started + timedelta(milliseconds=10),
        latency_ms=10,
        outcome=ProviderCallOutcome.FAILURE,
        failure_class=FailureClass.TRANSPORT,
        failure_code="connection_reset",
        failure_summary="connection reset",
    )
    assert failed.failure_class is FailureClass.TRANSPORT

    secret = "sk_test_abcdefghijklmnopqrstuvwxyz"
    redacted = ProviderCallRecord(
        logical_model_attempt=1,
        transport_attempt=1,
        provider="ollama",
        model="qwen2.5:3b",
        candidate_fingerprint="candidate:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        started_at=started,
        completed_at=started,
        latency_ms=0,
        outcome=ProviderCallOutcome.FAILURE,
        failure_class=FailureClass.AUTHENTICATION,
        failure_code="provider_authentication",
        failure_summary=f"Authorization: Bearer {secret}",
    )
    assert secret not in redacted.failure_summary

    with pytest.raises(ValueError, match="require a failure class"):
        ProviderCallRecord(
            logical_model_attempt=1,
            transport_attempt=1,
            provider="ollama",
            model="qwen2.5:3b",
            candidate_fingerprint="candidate:test",
            prompt_version="prompt:v1",
            schema_version="schema:v1",
            started_at=started,
            completed_at=started,
            latency_ms=0,
            outcome=ProviderCallOutcome.FAILURE,
        )
