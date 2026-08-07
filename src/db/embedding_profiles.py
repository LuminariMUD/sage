"""Authoritative PostgreSQL embedding-space metadata and read-only preflight."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from src.llm.provider_config import EmbeddingProfile

EMBEDDING_PROFILE_IMPLEMENTATION = "sage-provider-v1"
EMBEDDING_STORAGE_TYPE = "pgvector-vector-float4"
ACTIVATE_EMPTY_CONFIRMATION = "ACTIVATE_EMPTY_EMBEDDING_PROFILE"
ADOPT_EXISTING_CONFIRMATION = "ADOPT_EXISTING_EMBEDDING_PROFILE"

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VECTOR_TYPE = re.compile(r"^vector\((?P<dimensions>[1-9][0-9]*)\)$")


class EmbeddingSpaceError(RuntimeError):
    """Raised when a vector operation cannot safely use its configured space."""


@dataclass(frozen=True)
class EmbeddingSpaceSpec:
    """Checked-in physical contract for one PostgreSQL vector space."""

    semantic_index: str
    physical_space: str
    table_name: str
    column_name: str
    dimensions: int
    index_name: str
    index_method: str
    operator_class: str
    index_options: tuple[str, ...] = ()
    application_supported: bool = False


EPISODE_EMBEDDING_SPACE = EmbeddingSpaceSpec(
    semantic_index="episodes",
    physical_space="episodes.embedding",
    table_name="episodes",
    column_name="embedding",
    dimensions=768,
    index_name="idx_episodes_embedding",
    index_method="hnsw",
    operator_class="vector_cosine_ops",
    index_options=("m=16", "ef_construction=64"),
    application_supported=True,
)

LEGACY_CHUNK_EMBEDDING_SPACE = EmbeddingSpaceSpec(
    semantic_index="legacy_chunks",
    physical_space="chunks.embedding",
    table_name="chunks",
    column_name="embedding",
    dimensions=384,
    index_name="idx_chunks_embedding",
    index_method="ivfflat",
    operator_class="vector_cosine_ops",
    index_options=("lists=100",),
)

LEGACY_SEARCH_QUERY_SPACE = EmbeddingSpaceSpec(
    semantic_index="legacy_search_queries",
    physical_space="search_queries.query_embedding",
    table_name="search_queries",
    column_name="query_embedding",
    dimensions=384,
    index_name="idx_search_embedding",
    index_method="ivfflat",
    operator_class="vector_cosine_ops",
    index_options=("lists=50",),
)

EMBEDDING_SPACE_SPECS = MappingProxyType(
    {
        spec.semantic_index: spec
        for spec in (
            EPISODE_EMBEDDING_SPACE,
            LEGACY_CHUNK_EMBEDDING_SPACE,
            LEGACY_SEARCH_QUERY_SPACE,
        )
    }
)

_METADATA_TABLE_QUERY = """
    SELECT
        to_regclass('embedding_profiles')::text AS profiles_table,
        to_regclass('embedding_index_states')::text AS states_table
"""

_STATE_QUERY = """
    SELECT
        state.id::text AS id,
        state.semantic_index,
        state.physical_space,
        state.table_name,
        state.column_name,
        state.expected_dimensions,
        state.distance_metric,
        state.index_name,
        state.index_method,
        state.operator_class,
        state.state,
        state.profile_fingerprint,
        state.activated_at,
        profile.fingerprint AS stored_profile_fingerprint,
        profile.provider AS profile_provider,
        profile.endpoint_class AS profile_endpoint_class,
        profile.implementation AS profile_implementation,
        profile.model AS profile_model,
        profile.model_revision AS profile_model_revision,
        profile.dimensions AS profile_dimensions,
        profile.output_encoding AS profile_output_encoding,
        profile.storage_type AS profile_storage_type,
        profile.normalize AS profile_normalize,
        profile.distance_metric AS profile_distance_metric,
        profile.input_type AS profile_input_type
    FROM embedding_index_states AS state
    LEFT JOIN embedding_profiles AS profile
      ON profile.fingerprint = state.profile_fingerprint
    WHERE state.semantic_index = $1
    ORDER BY (state.state = 'active') DESC, state.created_at, state.id
"""

_COLUMN_QUERY = """
    SELECT format_type(attribute.atttypid, attribute.atttypmod) AS formatted_type
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = to_regclass($1)
      AND attribute.attname = $2
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
"""

_INDEX_QUERY = """
    SELECT
        access_method.amname AS method,
        operator_class.opcname AS operator_class,
        indexed_attribute.attname AS column_name,
        index_relation.reloptions AS options,
        index_metadata.indisvalid AS valid,
        index_metadata.indisready AS ready,
        index_metadata.indnkeyatts AS key_columns
    FROM pg_index AS index_metadata
    JOIN pg_class AS index_relation
      ON index_relation.oid = index_metadata.indexrelid
    JOIN pg_am AS access_method
      ON access_method.oid = index_relation.relam
    LEFT JOIN pg_opclass AS operator_class
      ON operator_class.oid = index_metadata.indclass[0]
    LEFT JOIN pg_attribute AS indexed_attribute
      ON indexed_attribute.attrelid = index_metadata.indrelid
     AND indexed_attribute.attnum = index_metadata.indkey[0]
    WHERE index_metadata.indrelid = to_regclass($1)
      AND index_relation.relname = $2
"""


def _endpoint_class(profile: EmbeddingProfile) -> str:
    provider = profile.connection.provider
    if provider == "sentence-transformers":
        return "in-process-sentence-transformers"
    if provider == "ollama":
        return "ollama-http"
    return "openai-compatible-http"


def embedding_profile_record(profile: EmbeddingProfile) -> dict[str, object]:
    """Return the secret-free record persisted for one profile fingerprint."""
    return {
        "fingerprint": profile.fingerprint,
        "provider": profile.connection.provider,
        "endpoint_class": _endpoint_class(profile),
        "implementation": EMBEDDING_PROFILE_IMPLEMENTATION,
        "model": profile.model,
        "model_revision": profile.revision,
        "dimensions": profile.dimensions,
        "output_encoding": profile.encoding_format,
        "storage_type": EMBEDDING_STORAGE_TYPE,
        "normalize": profile.normalize,
        "distance_metric": profile.distance_metric,
        "input_type": profile.input_type,
    }


def _safe_identifier(value: str) -> str:
    parts = value.split(".")
    if not parts or any(not _SQL_IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError("Embedding-space SQL identifier is invalid")
    return ".".join(parts)


def _row_dict(row: Any | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _finding(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _add_finding(
    findings: list[dict[str, str]],
    code: str,
    message: str,
    *,
    severity: str = "error",
) -> None:
    if not any(item["code"] == code for item in findings):
        findings.append(_finding(code, severity, message))


async def preflight_embedding_space(
    postgres: Any,
    spec: EmbeddingSpaceSpec,
    *,
    configured_profile: EmbeddingProfile | None = None,
    require_active: bool = True,
) -> dict[str, Any]:
    """Compare configured, recorded, and physical vector-space identities.

    The report contains only schema metadata, sanitized profile identity, and
    aggregate row counts. It never reads source text or vector values.
    """
    findings: list[dict[str, str]] = []
    metadata_available = False
    state_rows: list[dict[str, Any]] = []

    metadata_tables = _row_dict(await postgres.fetchrow(_METADATA_TABLE_QUERY)) or {}
    if metadata_tables.get("profiles_table") and metadata_tables.get("states_table"):
        metadata_available = True
        state_rows = [dict(row) for row in await postgres.fetch(_STATE_QUERY, spec.semantic_index)]
    else:
        _add_finding(
            findings,
            "metadata_tables_missing",
            "Embedding profile metadata has not been migrated",
        )

    matching_rows = [row for row in state_rows if row["physical_space"] == spec.physical_space]
    active_rows = [row for row in state_rows if row["state"] == "active"]
    selected_state: dict[str, Any] | None = None

    if len(active_rows) > 1:
        _add_finding(
            findings,
            "multiple_active_spaces",
            "More than one active space exists for the semantic index",
        )
    elif active_rows:
        selected_state = active_rows[0]
    elif matching_rows:
        selected_state = matching_rows[0]

    if metadata_available and not matching_rows:
        _add_finding(
            findings,
            "space_metadata_missing",
            "The checked-in physical space has no metadata record",
        )

    if require_active and not active_rows:
        _add_finding(
            findings,
            "active_space_missing",
            "The semantic index has no explicitly active embedding profile",
        )
    if active_rows and active_rows[0]["physical_space"] != spec.physical_space:
        _add_finding(
            findings,
            "unexpected_active_space",
            "The active physical space is not supported by this application revision",
        )

    if selected_state is not None:
        expected_state = {
            "semantic_index": spec.semantic_index,
            "physical_space": spec.physical_space,
            "table_name": spec.table_name,
            "column_name": spec.column_name,
            "expected_dimensions": spec.dimensions,
            "distance_metric": "cosine",
            "index_name": spec.index_name,
            "index_method": spec.index_method,
            "operator_class": spec.operator_class,
        }
        for field, expected in expected_state.items():
            if selected_state.get(field) != expected:
                _add_finding(
                    findings,
                    f"state_{field}_mismatch",
                    f"Embedding index-state field {field} does not match the checked-in contract",
                )

        if selected_state["state"] == "retired" and require_active:
            _add_finding(
                findings,
                "space_retired",
                "The requested embedding space is retired",
            )

    table_name = _safe_identifier(spec.table_name)
    column_name = _safe_identifier(spec.column_name)
    table_regclass = await postgres.fetchval("SELECT to_regclass($1)::text", spec.table_name)
    formatted_type: str | None = None
    physical_dimensions: int | None = None
    total_rows: int | None = None
    embedded_rows: int | None = None

    if table_regclass is None:
        _add_finding(findings, "table_missing", "The vector table does not exist")
    else:
        column_row = _row_dict(
            await postgres.fetchrow(_COLUMN_QUERY, spec.table_name, spec.column_name)
        )
        if column_row is None:
            _add_finding(findings, "vector_column_missing", "The vector column does not exist")
        else:
            formatted_type = str(column_row["formatted_type"])
            vector_match = _VECTOR_TYPE.fullmatch(formatted_type)
            if vector_match is None:
                _add_finding(
                    findings,
                    "vector_type_invalid",
                    "The configured column is not a fixed-dimension vector",
                )
            else:
                physical_dimensions = int(vector_match.group("dimensions"))
                if physical_dimensions != spec.dimensions:
                    _add_finding(
                        findings,
                        "physical_dimension_mismatch",
                        "The physical vector dimension does not match the checked-in contract",
                    )

            count_row = _row_dict(await postgres.fetchrow(f"""
                    SELECT count(*) AS total_rows,
                           count({column_name}) AS embedded_rows
                    FROM {table_name}
                    """))
            if count_row is not None:
                total_rows = int(count_row["total_rows"])
                embedded_rows = int(count_row["embedded_rows"])
                if embedded_rows != total_rows:
                    _add_finding(
                        findings,
                        "embedding_coverage_incomplete",
                        "Some rows do not have embeddings",
                        severity="warning",
                    )

    index_row = _row_dict(await postgres.fetchrow(_INDEX_QUERY, spec.table_name, spec.index_name))
    if index_row is None:
        _add_finding(findings, "index_missing", "The required vector index does not exist")
    else:
        index_options = sorted(index_row.get("options") or [])
        if index_row["method"] != spec.index_method:
            _add_finding(
                findings,
                "index_method_mismatch",
                "The vector index access method does not match the checked-in contract",
            )
        if index_row["operator_class"] != spec.operator_class:
            _add_finding(
                findings,
                "index_operator_class_mismatch",
                "The vector index operator class is incompatible",
            )
        if index_row["column_name"] != spec.column_name or index_row["key_columns"] != 1:
            _add_finding(
                findings,
                "index_column_mismatch",
                "The vector index does not cover exactly the expected column",
            )
        if not index_row["valid"]:
            _add_finding(findings, "index_invalid", "The vector index is invalid")
        if not index_row["ready"]:
            _add_finding(findings, "index_not_ready", "The vector index is not ready")
        for option in spec.index_options:
            if option not in index_options:
                _add_finding(
                    findings,
                    "index_options_mismatch",
                    "The vector index options do not match the checked-in contract",
                )

    configured_record = (
        embedding_profile_record(configured_profile) if configured_profile is not None else None
    )
    stored_record: dict[str, Any] | None = None
    if selected_state is not None and selected_state.get("stored_profile_fingerprint"):
        stored_record = {
            "fingerprint": selected_state["stored_profile_fingerprint"],
            "provider": selected_state["profile_provider"],
            "endpoint_class": selected_state["profile_endpoint_class"],
            "implementation": selected_state["profile_implementation"],
            "model": selected_state["profile_model"],
            "model_revision": selected_state["profile_model_revision"],
            "dimensions": selected_state["profile_dimensions"],
            "output_encoding": selected_state["profile_output_encoding"],
            "storage_type": selected_state["profile_storage_type"],
            "normalize": selected_state["profile_normalize"],
            "distance_metric": selected_state["profile_distance_metric"],
            "input_type": selected_state["profile_input_type"],
        }

    if configured_profile is not None:
        if configured_profile.dimensions != spec.dimensions:
            _add_finding(
                findings,
                "configured_dimension_mismatch",
                "The configured embedding dimension is incompatible with this physical space",
            )
        if selected_state is None or selected_state.get("profile_fingerprint") is None:
            _add_finding(
                findings,
                "stored_profile_missing",
                "The physical space has no persisted profile identity",
            )
        elif stored_record is None:
            _add_finding(
                findings,
                "stored_profile_unresolvable",
                "The active profile fingerprint has no immutable profile record",
            )
        else:
            for field, expected in configured_record.items():
                if stored_record.get(field) != expected:
                    code = (
                        "profile_fingerprint_mismatch"
                        if field == "fingerprint"
                        else f"profile_{field}_mismatch"
                    )
                    _add_finding(
                        findings,
                        code,
                        f"Stored embedding profile field {field} does not match configuration",
                    )

    errors = [finding for finding in findings if finding["severity"] == "error"]
    selected_status = selected_state["state"] if selected_state is not None else None
    if errors:
        status = "blocked"
    elif selected_status == "retired":
        status = "retired"
    elif require_active:
        status = "ready"
    else:
        status = "inventory"

    return {
        "schema_version": 1,
        "semantic_index": spec.semantic_index,
        "physical_space": spec.physical_space,
        "status": status,
        "ready": status == "ready",
        "configured_profile": configured_record,
        "metadata": {
            "available": metadata_available,
            "state": selected_status,
            "profile_fingerprint": (
                selected_state.get("profile_fingerprint") if selected_state is not None else None
            ),
            "expected_dimensions": (
                selected_state.get("expected_dimensions") if selected_state is not None else None
            ),
        },
        "physical": {
            "table": spec.table_name,
            "column": spec.column_name,
            "formatted_type": formatted_type,
            "dimensions": physical_dimensions,
            "total_rows": total_rows,
            "embedded_rows": embedded_rows,
            "missing_rows": (
                total_rows - embedded_rows
                if total_rows is not None and embedded_rows is not None
                else None
            ),
            "index": {
                "name": spec.index_name,
                "method": index_row.get("method") if index_row else None,
                "operator_class": index_row.get("operator_class") if index_row else None,
                "options": sorted(index_row.get("options") or []) if index_row else [],
                "valid": index_row.get("valid") if index_row else False,
                "ready": index_row.get("ready") if index_row else False,
            },
        },
        "findings": sorted(findings, key=lambda item: (item["severity"], item["code"])),
    }


def require_embedding_space(report: dict[str, Any]) -> None:
    """Raise a sanitized error when preflight did not establish readiness."""
    if report.get("ready"):
        return
    codes = sorted(
        finding["code"]
        for finding in report.get("findings", [])
        if finding.get("severity") == "error"
    )
    reason = ",".join(codes) if codes else "not_ready"
    raise EmbeddingSpaceError(f"Embedding space is unavailable ({reason})")


_ACTIVATION_IGNORED_CODES = frozenset(
    {
        "active_space_missing",
        "stored_profile_missing",
        "profile_fingerprint_mismatch",
        "profile_provider_mismatch",
        "profile_endpoint_class_mismatch",
        "profile_implementation_mismatch",
        "profile_model_mismatch",
        "profile_model_revision_mismatch",
        "profile_dimensions_mismatch",
        "profile_output_encoding_mismatch",
        "profile_storage_type_mismatch",
        "profile_normalize_mismatch",
        "profile_distance_metric_mismatch",
        "profile_input_type_mismatch",
    }
)


async def activate_embedding_space(
    postgres: Any,
    profile: EmbeddingProfile,
    spec: EmbeddingSpaceSpec = EPISODE_EMBEDDING_SPACE,
    *,
    adopt_existing: bool,
    confirmation: str,
) -> dict[str, Any]:
    """Persist and activate a profile after explicit provenance confirmation.

    This operation writes metadata only. It never creates vectors or calls a
    provider. Existing vectors require a stronger adoption token because their
    provenance cannot be inferred from dimensions alone.
    """
    if not spec.application_supported:
        raise EmbeddingSpaceError("Only the supported application space can be activated")

    inventory = await preflight_embedding_space(
        postgres,
        spec,
        configured_profile=profile,
        require_active=False,
    )
    blocking_codes = {
        finding["code"]
        for finding in inventory["findings"]
        if finding["severity"] == "error" and finding["code"] not in _ACTIVATION_IGNORED_CODES
    }
    if blocking_codes:
        reason = ",".join(sorted(blocking_codes))
        raise EmbeddingSpaceError(f"Embedding profile activation is blocked ({reason})")

    embedded_rows = int(inventory["physical"]["embedded_rows"] or 0)
    required_confirmation = (
        ADOPT_EXISTING_CONFIRMATION if embedded_rows else ACTIVATE_EMPTY_CONFIRMATION
    )
    if bool(embedded_rows) != adopt_existing:
        if embedded_rows:
            raise EmbeddingSpaceError("Existing embeddings require explicit profile adoption")
        raise EmbeddingSpaceError("Empty embedding spaces cannot use existing-vector adoption")
    if confirmation != required_confirmation:
        raise EmbeddingSpaceError("Embedding profile activation confirmation is invalid")

    record = embedding_profile_record(profile)
    columns = tuple(record)
    values = tuple(record[column] for column in columns)
    placeholders = ", ".join(f"${index}" for index in range(1, len(values) + 1))
    insert_columns = ", ".join(columns)

    async with postgres.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('sage:embedding-profile-activation'))"
            )
            # Hold the physical relation stable while rechecking catalogs, counts,
            # and metadata on this same transaction/connection. The lock window is
            # limited to metadata insertion and activation.
            await connection.execute(
                f"LOCK TABLE {_safe_identifier(spec.table_name)} IN SHARE MODE"
            )
            locked_inventory = await preflight_embedding_space(
                connection,
                spec,
                configured_profile=profile,
                require_active=False,
            )
            locked_blockers = {
                finding["code"]
                for finding in locked_inventory["findings"]
                if finding["severity"] == "error"
                and finding["code"] not in _ACTIVATION_IGNORED_CODES
            }
            if locked_blockers:
                reason = ",".join(sorted(locked_blockers))
                raise EmbeddingSpaceError(f"Embedding profile activation is blocked ({reason})")
            locked_embedded_rows = int(locked_inventory["physical"]["embedded_rows"] or 0)
            if bool(locked_embedded_rows) != adopt_existing:
                raise EmbeddingSpaceError("Embedding row coverage changed during activation")

            state = await connection.fetchrow(
                """
                SELECT id, state, profile_fingerprint
                FROM embedding_index_states
                WHERE semantic_index = $1
                  AND physical_space = $2
                FOR UPDATE
                """,
                spec.semantic_index,
                spec.physical_space,
            )
            if state is None:
                raise EmbeddingSpaceError("Embedding index-state metadata is missing")
            if state["state"] == "retired":
                raise EmbeddingSpaceError("A retired embedding space cannot be activated")
            if state["state"] == "active" and state["profile_fingerprint"] != profile.fingerprint:
                raise EmbeddingSpaceError("A different embedding profile is already active")

            await connection.execute(
                f"""
                INSERT INTO embedding_profiles ({insert_columns})
                VALUES ({placeholders})
                ON CONFLICT (fingerprint) DO NOTHING
                """,
                *values,
            )
            stored = await connection.fetchrow(
                """
                SELECT fingerprint, provider, endpoint_class, implementation,
                       model, model_revision, dimensions, output_encoding,
                       storage_type, normalize, distance_metric, input_type
                FROM embedding_profiles
                WHERE fingerprint = $1
                """,
                profile.fingerprint,
            )
            if stored is None or any(stored[column] != record[column] for column in columns):
                raise EmbeddingSpaceError("Stored embedding profile identity is inconsistent")

            await connection.execute(
                """
                UPDATE embedding_index_states
                SET state = 'active',
                    profile_fingerprint = $3,
                    activated_at = COALESCE(activated_at, clock_timestamp()),
                    updated_at = clock_timestamp()
                WHERE semantic_index = $1
                  AND physical_space = $2
                """,
                spec.semantic_index,
                spec.physical_space,
                profile.fingerprint,
            )

    return await preflight_embedding_space(
        postgres,
        spec,
        configured_profile=profile,
        require_active=True,
    )
