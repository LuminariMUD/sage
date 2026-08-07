"""Unit tests for durable Graphiti lifecycle contracts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from src.graphiti.sync_failures import classify_sync_failure
from src.graphiti.sync_models import (
    FailureClass,
    FailureDisposition,
    FailureRecord,
    GraphSyncPolicy,
    ProviderCallIntent,
    ProviderCallOutcome,
    ProviderCallRecord,
    StableIdVerification,
    deterministic_retry_delay,
    sanitize_summary,
)
from src.llm.retry import (
    MalformedModelOutputError,
    ModelOutputLimitError,
    ModelSchemaValidationError,
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


def test_schema_failure_summary_never_retains_invalid_model_content():
    class RequiredOutput(BaseModel):
        count: int

    sensitive_output = "private lore output that must not enter the ledger"
    try:
        RequiredOutput.model_validate({"count": sensitive_output})
    except ValidationError as error:
        failure = classify_sync_failure(error)
    else:
        raise AssertionError("Invalid model output unexpectedly passed validation")

    assert failure.failure_class is FailureClass.SCHEMA_VALIDATION
    assert failure.summary == "Model output failed schema validation"
    assert sensitive_output not in failure.summary


@pytest.mark.parametrize(
    ("error", "failure_class", "summary"),
    [
        (
            MalformedModelOutputError("private malformed model output"),
            FailureClass.MALFORMED_JSON,
            "Model output could not be decoded as JSON",
        ),
        (
            ModelSchemaValidationError("private schema-invalid model output"),
            FailureClass.SCHEMA_VALIDATION,
            "Model output failed schema validation",
        ),
        (
            ModelOutputLimitError("private truncated model output"),
            FailureClass.OUTPUT_LIMIT,
            "Model output reached its configured limit",
        ),
    ],
)
def test_model_output_failures_use_stable_content_free_taxonomy(error, failure_class, summary):
    failure = classify_sync_failure(error)

    assert failure.failure_class is failure_class
    assert failure.summary == summary
    assert "private" not in failure.summary


@pytest.mark.parametrize(
    ("status_code", "failure_class", "code", "disposition"),
    [
        (402, FailureClass.RESOURCE_EXHAUSTION, "provider_resource_exhausted", "pause_systemic"),
        (408, FailureClass.TRANSPORT, "provider_http_transient", "retry"),
        (409, FailureClass.TRANSPORT, "provider_http_transient", "retry"),
        (422, FailureClass.CONFIGURATION, "provider_request_rejected", "pause_systemic"),
        (503, FailureClass.TRANSPORT, "provider_http_transient", "retry"),
    ],
)
def test_provider_http_failures_keep_route_and_durable_taxonomy_aligned(
    status_code, failure_class, code, disposition
):
    class ProviderHTTPError(RuntimeError):
        pass

    error = ProviderHTTPError("private upstream detail")
    error.status_code = status_code
    failure = classify_sync_failure(error)

    assert failure.failure_class is failure_class
    assert failure.code == code
    assert failure.disposition.value == disposition


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
    intent = ProviderCallIntent.from_record(failed)
    assert intent.model == failed.model
    assert intent.started_at == failed.started_at

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


def test_provider_call_rejects_naive_timestamps():
    naive = datetime.now()
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderCallIntent(
            logical_model_attempt=1,
            transport_attempt=1,
            provider="ollama",
            model="qwen2.5:3b",
            candidate_fingerprint="candidate:test",
            prompt_version="prompt:v1",
            schema_version="schema:v1",
            started_at=naive,
        )


def test_stable_verification_requires_independent_source_and_profile_counts():
    base = {
        "stable_id": "11111111-1111-1111-1111-111111111111",
        "candidate_count": 1,
        "stable_id_count": 1,
        "source_description_count": 1,
        "exact_count": 1,
        "source_fingerprint": "sha256:v1:test",
        "sync_profile_fingerprint": "sync:test",
        "source_fingerprint_count": 1,
        "sync_profile_fingerprint_count": 1,
    }

    assert StableIdVerification(**base).is_exact
    assert not StableIdVerification(**{**base, "source_fingerprint_count": 0}).is_exact
    assert not StableIdVerification(
        **base,
        embedding_profile_fingerprint="embedding:test",
        embedding_profile_fingerprint_count=0,
    ).is_exact
