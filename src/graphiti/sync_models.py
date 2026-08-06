"""Typed contracts for the durable Graphiti synchronization lifecycle."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from src.security import redact_sensitive_text


class GraphSyncStateError(RuntimeError):
    """Base error for rejected durable-state operations."""


class RunUnavailableError(GraphSyncStateError):
    """Raised when an active run cannot accept a requested operation."""


class LeaseLostError(GraphSyncStateError):
    """Raised when a worker no longer owns a valid lease."""


class InvalidTransitionError(GraphSyncStateError):
    """Raised when a lifecycle transition violates the state machine."""


class JobState(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    RETRY_WAIT = "retry_wait"
    QUARANTINED = "quarantined"
    SYNCED = "synced"


class RunState(str, Enum):
    RUNNING = "running"
    DRAINING = "draining"
    PAUSED_SYSTEMIC = "paused_systemic"
    STOPPED = "stopped"


class FailureClass(str, Enum):
    TRANSPORT = "transport"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFIGURATION = "configuration"
    PROFILE_MISMATCH = "profile_mismatch"
    RATE_LIMIT = "rate_limit"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    OUTPUT_LIMIT = "output_limit"
    MALFORMED_JSON = "malformed_json"
    SCHEMA_VALIDATION = "schema_validation"
    GRAPH_VALIDATION = "graph_validation"
    PERSISTENCE = "persistence"
    VERIFICATION = "verification"
    CANCELLATION = "cancellation"
    SHUTDOWN = "shutdown"
    INTERNAL = "internal"


class FailureDisposition(str, Enum):
    RETRY = "retry"
    QUARANTINE = "quarantine"
    PAUSE_SYSTEMIC = "pause_systemic"
    CANCEL = "cancel"
    SHUTDOWN = "shutdown"


class AttemptOutcome(str, Enum):
    PRIMARY_SUCCESS = "primary_success"
    FALLBACK_SUCCESS = "fallback_success"
    RETRY_WAIT = "retry_wait"
    QUARANTINED = "quarantined"
    PAUSED_SYSTEMIC = "paused_systemic"
    CANCELLED = "cancelled"
    SHUTDOWN = "shutdown"


class ProviderCallOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class CompletionStatus(str, Enum):
    SYNCED = "synced"
    RETRY_WAIT = "retry_wait"
    QUARANTINED = "quarantined"
    PAUSED_SYSTEMIC = "paused_systemic"
    SOURCE_CHANGED = "source_changed"
    ALREADY_COMPLETED = "already_completed"


_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]+")


def validate_label(value: str, label: str, *, maximum: int = 255) -> str:
    """Validate a bounded printable label without exposing its value in errors."""
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} is missing or too long")
    if any(ord(character) < 32 or ord(character) > 126 for character in value):
        raise ValueError(f"{label} contains unsupported characters")
    return value


def validate_failure_code(value: str) -> str:
    """Validate a stable, bounded failure code."""
    if not isinstance(value, str) or not _SAFE_CODE.fullmatch(value):
        raise ValueError("Failure code is invalid")
    return value


def sanitize_summary(value: object, *, maximum: int = 512) -> str:
    """Redact credentials, collapse controls, and bound operator-visible text."""
    redacted = redact_sensitive_text(value)
    collapsed = _CONTROL_OR_SPACE.sub(" ", redacted).strip()
    if not collapsed:
        return "No sanitized detail available"
    return collapsed[:maximum]


def deterministic_retry_delay(
    episode_id: UUID,
    budget_attempt_number: int,
    *,
    base_seconds: int,
    maximum_seconds: int,
) -> int:
    """Return bounded exponential backoff with stable per-attempt jitter."""
    if budget_attempt_number <= 0:
        raise ValueError("Budget attempt number must be positive")
    if base_seconds <= 0 or maximum_seconds < base_seconds:
        raise ValueError("Retry delay bounds are invalid")

    exponent = min(budget_attempt_number - 1, 30)
    raw_delay = min(maximum_seconds, base_seconds * (2**exponent))
    seed = f"{episode_id}:{budget_attempt_number}".encode("ascii")
    fraction = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") / ((2**64) - 1)
    jittered = round(raw_delay * (0.8 + (0.4 * fraction)))
    return max(1, min(maximum_seconds, jittered))


@dataclass(frozen=True)
class GraphSyncPolicy:
    """Validated policy captured into every claimed attempt."""

    lease_seconds: int = 900
    max_job_attempts: int = 3
    retry_base_seconds: int = 60
    retry_max_seconds: int = 3600
    max_provider_calls: int = 3

    def __post_init__(self) -> None:
        if not 30 <= self.lease_seconds <= 86_400:
            raise ValueError("Lease seconds must be between 30 and 86400")
        if not 1 <= self.max_job_attempts <= 100:
            raise ValueError("Maximum job attempts must be between 1 and 100")
        if not 1 <= self.retry_base_seconds <= self.retry_max_seconds:
            raise ValueError("Retry delay bounds are invalid")
        if self.retry_max_seconds > 604_800:
            raise ValueError("Maximum retry delay cannot exceed seven days")
        if not 1 <= self.max_provider_calls <= 100:
            raise ValueError("Maximum provider calls must be between 1 and 100")


@dataclass(frozen=True)
class RunRecord:
    id: UUID
    state: RunState
    worker_id: str
    sync_profile_fingerprint: str
    started_at: datetime
    heartbeat_at: datetime


@dataclass(frozen=True)
class JobLease:
    episode_id: UUID
    attempt_id: UUID
    run_id: UUID
    lease_token: UUID
    lease_owner: str
    attempt_number: int
    budget_attempt_number: int
    retry_generation: int
    captured_source_fingerprint: str
    sync_profile_fingerprint: str
    route_fingerprint: str
    lease_expires_at: datetime
    text: str
    document_id: UUID
    episode_index: int
    created_at: datetime


@dataclass(frozen=True)
class FailureRecord:
    failure_class: FailureClass
    code: str
    summary: str
    disposition: FailureDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.failure_class, FailureClass):
            raise ValueError("Failure class is invalid")
        if not isinstance(self.disposition, FailureDisposition):
            raise ValueError("Failure disposition is invalid")
        object.__setattr__(self, "code", validate_failure_code(self.code))
        object.__setattr__(self, "summary", sanitize_summary(self.summary))

    @classmethod
    def build(
        cls,
        *,
        failure_class: FailureClass,
        code: str,
        summary: object,
        disposition: FailureDisposition,
    ) -> FailureRecord:
        return cls(
            failure_class=failure_class,
            code=code,
            summary=str(summary),
            disposition=disposition,
        )


@dataclass(frozen=True)
class ProviderCallRecord:
    logical_model_attempt: int
    transport_attempt: int
    provider: str
    model: str
    candidate_fingerprint: str
    prompt_version: str
    schema_version: str
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    outcome: ProviderCallOutcome
    model_revision: str | None = None
    actual_model: str | None = None
    actual_upstream_provider: str | None = None
    failure_class: FailureClass | None = None
    failure_code: str | None = None
    failure_summary: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ProviderCallOutcome):
            raise ValueError("Provider call outcome is invalid")
        if self.failure_class is not None and not isinstance(self.failure_class, FailureClass):
            raise ValueError("Provider call failure class is invalid")
        if self.logical_model_attempt <= 0 or self.transport_attempt <= 0:
            raise ValueError("Provider attempt numbers must be positive")
        if self.completed_at < self.started_at or self.latency_ms < 0:
            raise ValueError("Provider call timing is invalid")
        for value, label in (
            (self.provider, "Provider"),
            (self.model, "Model"),
            (self.candidate_fingerprint, "Candidate fingerprint"),
            (self.prompt_version, "Prompt version"),
            (self.schema_version, "Schema version"),
        ):
            validate_label(value, label)
        if self.outcome is ProviderCallOutcome.SUCCESS and self.failure_class is not None:
            raise ValueError("Successful provider calls cannot have a failure class")
        if self.outcome is not ProviderCallOutcome.SUCCESS and self.failure_class is None:
            raise ValueError("Failed provider calls require a failure class")
        if self.failure_code is not None:
            object.__setattr__(self, "failure_code", validate_failure_code(self.failure_code))
        if self.failure_summary is not None:
            object.__setattr__(self, "failure_summary", sanitize_summary(self.failure_summary))
        for token_count in (self.prompt_tokens, self.completion_tokens, self.total_tokens):
            if token_count is not None and token_count < 0:
                raise ValueError("Token counts cannot be negative")


@dataclass(frozen=True)
class StableIdVerification:
    stable_id: str
    candidate_count: int
    stable_id_count: int
    source_description_count: int
    exact_count: int
    source_fingerprint: str
    sync_profile_fingerprint: str

    @property
    def is_exact(self) -> bool:
        return (
            self.candidate_count == 1
            and self.stable_id_count == 1
            and self.source_description_count == 1
            and self.exact_count == 1
        )


@dataclass(frozen=True)
class GraphCounts:
    proposed_entities: int | None = None
    accepted_entities: int | None = None
    rejected_entities: int | None = None
    proposed_edges: int | None = None
    accepted_edges: int | None = None
    rejected_edges: int | None = None

    def __post_init__(self) -> None:
        values = (
            self.proposed_entities,
            self.accepted_entities,
            self.rejected_entities,
            self.proposed_edges,
            self.accepted_edges,
            self.rejected_edges,
        )
        if any(value is not None and value < 0 for value in values):
            raise ValueError("Graph counts cannot be negative")
