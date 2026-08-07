"""Stable failure classification for durable Graphiti synchronization."""

from __future__ import annotations

import asyncio
import json

from src.graphiti.sync_graph import GraphIdentityConflictError, GraphVerificationError
from src.graphiti.sync_models import (
    FailureClass,
    FailureDisposition,
    FailureRecord,
    ProfileMismatchError,
    ProviderCallLimitExceeded,
)
from src.llm.retry import (
    MalformedModelOutputError,
    ModelOutputLimitError,
    ModelSchemaValidationError,
)


def _status_code(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def classify_sync_failure(error: BaseException, *, shutting_down: bool = False) -> FailureRecord:
    """Map an exception to one sanitized, stable lifecycle disposition."""
    name = type(error).__name__.lower()
    module = type(error).__module__.lower()
    status = _status_code(error)

    if shutting_down:
        return FailureRecord.build(
            failure_class=FailureClass.SHUTDOWN,
            code="worker_shutdown",
            summary="Worker shutdown interrupted the active episode",
            disposition=FailureDisposition.SHUTDOWN,
        )
    if isinstance(error, asyncio.CancelledError):
        return FailureRecord.build(
            failure_class=FailureClass.CANCELLATION,
            code="worker_cancelled",
            summary="Worker task was cancelled",
            disposition=FailureDisposition.CANCEL,
        )
    if isinstance(error, ProviderCallLimitExceeded):
        return FailureRecord.build(
            failure_class=FailureClass.RESOURCE_EXHAUSTION,
            code="provider_call_limit_exhausted",
            summary=error,
            disposition=FailureDisposition.RETRY,
        )
    if isinstance(error, ProfileMismatchError):
        return FailureRecord.build(
            failure_class=FailureClass.PROFILE_MISMATCH,
            code="sync_profile_mismatch",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if isinstance(error, GraphIdentityConflictError):
        return FailureRecord.build(
            failure_class=FailureClass.GRAPH_VALIDATION,
            code="graph_identity_conflict",
            summary=error,
            disposition=FailureDisposition.QUARANTINE,
        )
    if isinstance(error, GraphVerificationError):
        return FailureRecord.build(
            failure_class=FailureClass.VERIFICATION,
            code="graph_verification_failed",
            summary=error,
            disposition=FailureDisposition.RETRY,
        )
    if (
        isinstance(error, (MalformedModelOutputError, json.JSONDecodeError))
        or "jsondecode" in name
        or "emptyresponse" in name
    ):
        return FailureRecord.build(
            failure_class=FailureClass.MALFORMED_JSON,
            code="malformed_model_output",
            summary="Model output could not be decoded as JSON",
            disposition=FailureDisposition.RETRY,
        )
    if status == 401 or "authentication" in name or "autherror" in name:
        return FailureRecord.build(
            failure_class=FailureClass.AUTHENTICATION,
            code="provider_authentication",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if status == 403 or "permissiondenied" in name or "authorization" in name:
        return FailureRecord.build(
            failure_class=FailureClass.AUTHORIZATION,
            code="provider_authorization",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if status == 402 or any(
        marker in name for marker in ("insufficientquota", "quotaexceeded", "resourceexhausted")
    ):
        return FailureRecord.build(
            failure_class=FailureClass.RESOURCE_EXHAUSTION,
            code="provider_resource_exhausted",
            summary="Provider resource is exhausted",
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if status == 429 or "ratelimit" in name:
        return FailureRecord.build(
            failure_class=FailureClass.RATE_LIMIT,
            code="provider_rate_limit",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if isinstance(error, ModelOutputLimitError):
        return FailureRecord.build(
            failure_class=FailureClass.OUTPUT_LIMIT,
            code="model_output_limit",
            summary="Model output reached its configured limit",
            disposition=FailureDisposition.RETRY,
        )
    if isinstance(error, ModelSchemaValidationError) or "validationerror" in name:
        return FailureRecord.build(
            failure_class=FailureClass.SCHEMA_VALIDATION,
            code="model_schema_invalid",
            summary="Model output failed schema validation",
            disposition=FailureDisposition.RETRY,
        )
    if "neo4j" in module or "neo4j" in name or "sessionexpired" in name:
        return FailureRecord.build(
            failure_class=FailureClass.PERSISTENCE,
            code="graph_store_unavailable",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if "providerledger" in name or "databas" in name or "postgres" in name:
        return FailureRecord.build(
            failure_class=FailureClass.PERSISTENCE,
            code="sync_ledger_unavailable",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if status in {408, 409} or (status is not None and status >= 500):
        return FailureRecord.build(
            failure_class=FailureClass.TRANSPORT,
            code="provider_http_transient",
            summary=error,
            disposition=FailureDisposition.RETRY,
        )
    if (
        isinstance(error, (TimeoutError, ConnectionError))
        or any(marker in name for marker in ("timeout", "connect", "transport", "network"))
        or "serviceunavailable" in name
    ):
        return FailureRecord.build(
            failure_class=FailureClass.TRANSPORT,
            code="provider_transport",
            summary=error,
            disposition=FailureDisposition.RETRY,
        )
    if status is not None and 400 <= status < 500:
        return FailureRecord.build(
            failure_class=FailureClass.CONFIGURATION,
            code="provider_request_rejected",
            summary="Provider rejected the request configuration",
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    if isinstance(error, ValueError) or "configuration" in name:
        return FailureRecord.build(
            failure_class=FailureClass.CONFIGURATION,
            code="invalid_configuration",
            summary=error,
            disposition=FailureDisposition.PAUSE_SYSTEMIC,
        )
    return FailureRecord.build(
        failure_class=FailureClass.INTERNAL,
        code="unclassified_runtime_error",
        summary=error,
        disposition=FailureDisposition.RETRY,
    )
