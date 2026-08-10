"""Content-addressed semantic chunk manifests and section-role policy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

CHUNK_MANIFEST_SCHEMA_VERSION = 1
CONTENT_ROLE_POLICY_INCLUDE_ALL = "include_all_v1"
CONTENT_ROLE_POLICY_EXCLUDE_NON_LORE = "exclude_non_lore_v1"
CONTENT_ROLE_POLICIES = frozenset(
    {CONTENT_ROLE_POLICY_INCLUDE_ALL, CONTENT_ROLE_POLICY_EXCLUDE_NON_LORE}
)

WORLD_LORE = "world_lore"
RUNTIME_CONTRACT = "runtime_contract"
PRESENTATION_GUIDANCE = "presentation_guidance"
SCHEMA_GUIDANCE = "schema_guidance"
MIGRATION_GUIDANCE = "migration_guidance"
MIXED = "mixed"

_HEADING = re.compile(r"^(?P<level>#{1,6})[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
_CONTINUATION = re.compile(r"^\[Continuing from [^\]]+\]\s*", re.IGNORECASE)
_SPACE = re.compile(r"\s+")

_ROLE_RULES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        RUNTIME_CONTRACT,
        (
            re.compile(r"\bruntime\b"),
            re.compile(r"\bintegration contract\b"),
            re.compile(r"\bstable id\b"),
            re.compile(r"\bmedia key\b"),
            re.compile(r"\bmechanical-purpose\b"),
        ),
    ),
    (
        MIGRATION_GUIDANCE,
        (
            re.compile(r"\bmigration\b"),
            re.compile(r"\bbackward compatibility\b"),
            re.compile(r"\blegacy conversion\b"),
            re.compile(r"\bdeprecation\b"),
        ),
    ),
    (
        SCHEMA_GUIDANCE,
        (
            re.compile(r"\bschema\b"),
            re.compile(r"\bdatabase field\b"),
            re.compile(r"\bmetadata field\b"),
            re.compile(r"\bfield contract\b"),
        ),
    ),
    (
        PRESENTATION_GUIDANCE,
        (
            re.compile(r"\bplayer presentation\b"),
            re.compile(r"\bui contract\b"),
            re.compile(r"\bcard summary\b"),
            re.compile(r"\bdisplay guidance\b"),
        ),
    ),
)


def _canonical_fingerprint(prefix: str, value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return f"{prefix}:sha256:{hashlib.sha256(payload).hexdigest()}"


def source_fingerprint(text: str) -> str:
    """Return the durable source fingerprint used by graph sync."""
    return f"sha256:v1:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def resolve_content_role_policy(value: str | None) -> str:
    """Normalize a configured content-role policy or fail closed."""
    parsed = (value or CONTENT_ROLE_POLICY_INCLUDE_ALL).strip().lower()
    if parsed not in CONTENT_ROLE_POLICIES:
        raise ValueError("Content-role policy is unsupported")
    return parsed


@dataclass(frozen=True)
class ChunkingProfile:
    """Versioned inputs that can affect semantic chunk identity."""

    base_tokens: int
    min_tokens: int
    max_tokens: int
    overlap_percentage: float
    similarity_threshold: float
    complexity_factor: float
    embedding_model: str
    embedding_revision: str | None
    tokenizer: str
    sentence_segmenter: str
    content_role_policy: str

    def __post_init__(self) -> None:
        resolve_content_role_policy(self.content_role_policy)
        if not 1 <= self.min_tokens <= self.base_tokens <= self.max_tokens:
            raise ValueError("Chunk token bounds are invalid")
        if not 0 <= self.overlap_percentage < 1:
            raise ValueError("Chunk overlap percentage is invalid")
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("Chunk similarity threshold is invalid")
        if self.complexity_factor <= 0:
            raise ValueError("Chunk complexity factor is invalid")

    def contract(self) -> dict[str, object]:
        return {
            "schema_version": CHUNK_MANIFEST_SCHEMA_VERSION,
            "base_tokens": self.base_tokens,
            "min_tokens": self.min_tokens,
            "max_tokens": self.max_tokens,
            "overlap_percentage": self.overlap_percentage,
            "similarity_threshold": self.similarity_threshold,
            "complexity_factor": self.complexity_factor,
            "embedding_model": self.embedding_model,
            "embedding_revision": self.embedding_revision,
            "tokenizer": self.tokenizer,
            "sentence_segmenter": self.sentence_segmenter,
            "content_role_policy": self.content_role_policy,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_fingerprint("chunk-profile", self.contract())


@dataclass(frozen=True)
class ChunkManifestItem:
    episode_index: int
    text: str
    content_fingerprint: str
    content_role: str
    graph_extraction_eligible: bool

    def identity(self) -> dict[str, object]:
        return {
            "episode_index": self.episode_index,
            "content_fingerprint": self.content_fingerprint,
            "content_role": self.content_role,
            "graph_extraction_eligible": self.graph_extraction_eligible,
        }


@dataclass(frozen=True)
class ChunkManifest:
    document_source_fingerprint: str
    profile: ChunkingProfile
    items: tuple[ChunkManifestItem, ...]

    @property
    def fingerprint(self) -> str:
        return _canonical_fingerprint(
            "chunk-manifest",
            {
                "schema_version": CHUNK_MANIFEST_SCHEMA_VERSION,
                "document_source_fingerprint": self.document_source_fingerprint,
                "chunk_profile_fingerprint": self.profile.fingerprint,
                "items": [item.identity() for item in self.items],
            },
        )


@dataclass(frozen=True)
class _MarkdownSection:
    heading: str
    normalized_body: str
    role: str


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", value.casefold()).strip()


def _role_from_evidence(heading: str, body: str) -> str:
    normalized_heading = _normalize(heading)
    normalized_body = _normalize(body[:2_000])
    matched: list[str] = []
    for role, patterns in _ROLE_RULES:
        heading_match = any(pattern.search(normalized_heading) for pattern in patterns)
        body_matches = sum(bool(pattern.search(normalized_body)) for pattern in patterns)
        if heading_match or body_matches >= 2:
            matched.append(role)
    if not matched:
        return WORLD_LORE
    return matched[0] if len(matched) == 1 else MIXED


def parse_markdown_sections(markdown: str) -> tuple[_MarkdownSection, ...]:
    """Split Markdown by headings and assign conservative content roles."""
    matches = list(_HEADING.finditer(markdown))
    if not matches:
        return (
            _MarkdownSection(
                heading="",
                normalized_body=_normalize(markdown),
                role=_role_from_evidence("", markdown),
            ),
        )

    sections: list[_MarkdownSection] = []
    if matches[0].start() > 0 and markdown[: matches[0].start()].strip():
        preamble = markdown[: matches[0].start()]
        sections.append(
            _MarkdownSection(
                heading="",
                normalized_body=_normalize(preamble),
                role=_role_from_evidence("", preamble),
            )
        )
    heading_stack: list[tuple[int, str]] = []
    for position, match in enumerate(matches):
        level = len(match.group("level"))
        heading = match.group("title").strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown)
        body = markdown[match.end() : end]
        heading_path = " / ".join(item[1] for item in heading_stack)
        sections.append(
            _MarkdownSection(
                heading=heading_path,
                normalized_body=_normalize(body),
                role=_role_from_evidence(heading_path, body),
            )
        )
    return tuple(sections)


def classify_chunk_role(chunk_text: str, sections: tuple[_MarkdownSection, ...]) -> str:
    """Map a generated chunk back to its source section without storing offsets."""
    normalized = _normalize(_CONTINUATION.sub("", chunk_text))
    if not normalized:
        return WORLD_LORE
    probe = normalized[:160]
    matched_roles = {
        section.role
        for section in sections
        if probe in section.normalized_body
        or (len(probe) > 80 and probe[:80] in section.normalized_body)
    }
    if len(matched_roles) == 1:
        return next(iter(matched_roles))
    if len(matched_roles) > 1:
        return MIXED
    return _role_from_evidence("", normalized)


def build_chunk_manifest(
    document_text: str,
    chunks: list[dict[str, Any]],
    profile: ChunkingProfile,
) -> ChunkManifest:
    """Build a deterministic manifest from semantic chunker output."""
    sections = parse_markdown_sections(document_text)
    policy = resolve_content_role_policy(profile.content_role_policy)
    items = []
    for index, chunk in enumerate(chunks):
        text = chunk.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Semantic chunk text is missing")
        role = classify_chunk_role(text, sections)
        eligible = policy == CONTENT_ROLE_POLICY_INCLUDE_ALL or role == WORLD_LORE
        items.append(
            ChunkManifestItem(
                episode_index=index,
                text=text,
                content_fingerprint=source_fingerprint(text),
                content_role=role,
                graph_extraction_eligible=eligible,
            )
        )
    return ChunkManifest(
        document_source_fingerprint=source_fingerprint(document_text),
        profile=profile,
        items=tuple(items),
    )


async def reconcile_document_manifest(
    connection: Any,
    document: Any,
    manifest: ChunkManifest,
) -> dict[str, int | str]:
    """Atomically activate expected chunks and retire every obsolete index."""
    document_id = document["id"]
    previous_manifest_id = await connection.fetchval(
        "SELECT active_chunk_manifest_id FROM lore_documents WHERE id = $1 FOR UPDATE",
        document_id,
    )
    manifest_id = await connection.fetchval(
        """
        INSERT INTO document_chunk_manifests (
            document_id,
            document_source_fingerprint,
            chunk_profile_fingerprint,
            content_role_policy,
            manifest_fingerprint,
            chunk_count,
            predecessor_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (document_id, manifest_fingerprint) DO NOTHING
        RETURNING id
        """,
        document_id,
        manifest.document_source_fingerprint,
        manifest.profile.fingerprint,
        manifest.profile.content_role_policy,
        manifest.fingerprint,
        len(manifest.items),
        previous_manifest_id,
    )
    if manifest_id is None:
        manifest_id = await connection.fetchval(
            """
            SELECT id
            FROM document_chunk_manifests
            WHERE document_id = $1 AND manifest_fingerprint = $2
            """,
            document_id,
            manifest.fingerprint,
        )
    if manifest_id is None:
        raise RuntimeError("Chunk manifest identity could not be resolved")
    existing_rows = await connection.fetch(
        """
        SELECT id, episode_index, retired_at
        FROM episodes
        WHERE document_id = $1
        FOR UPDATE
        """,
        document_id,
    )
    existing = {int(row["episode_index"]): row for row in existing_rows}
    activated = 0
    created = 0
    for item in manifest.items:
        await connection.execute(
            """
            INSERT INTO document_chunk_manifest_items (
                manifest_id,
                episode_index,
                content_fingerprint,
                content_role,
                graph_extraction_eligible
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (manifest_id, episode_index) DO NOTHING
            """,
            manifest_id,
            item.episode_index,
            item.content_fingerprint,
            item.content_role,
            item.graph_extraction_eligible,
        )
        episode_id = await connection.fetchval(
            """
            INSERT INTO episodes (
                document_id,
                episode_index,
                text,
                chunk_profile_fingerprint,
                chunk_manifest_fingerprint,
                chunk_manifest_id,
                content_fingerprint,
                content_role,
                content_role_policy,
                graph_extraction_eligible,
                retired_at,
                retirement_reason_code,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NULL, NULL, NOW(), NOW())
            ON CONFLICT (document_id, episode_index) DO UPDATE
            SET text = EXCLUDED.text,
                embedding = CASE
                    WHEN episodes.text IS DISTINCT FROM EXCLUDED.text
                      OR episodes.retired_at IS NOT NULL THEN NULL
                    ELSE episodes.embedding
                END,
                chunk_profile_fingerprint = EXCLUDED.chunk_profile_fingerprint,
                chunk_manifest_fingerprint = EXCLUDED.chunk_manifest_fingerprint,
                chunk_manifest_id = EXCLUDED.chunk_manifest_id,
                content_fingerprint = EXCLUDED.content_fingerprint,
                content_role = EXCLUDED.content_role,
                content_role_policy = EXCLUDED.content_role_policy,
                graph_extraction_eligible = EXCLUDED.graph_extraction_eligible,
                retired_at = NULL,
                retirement_reason_code = NULL,
                updated_at = NOW()
            RETURNING id
            """,
            document_id,
            item.episode_index,
            item.text,
            manifest.profile.fingerprint,
            manifest.fingerprint,
            manifest_id,
            item.content_fingerprint,
            item.content_role,
            manifest.profile.content_role_policy,
            item.graph_extraction_eligible,
        )
        previous = existing.get(item.episode_index)
        if previous is None:
            created += 1
            await connection.execute(
                """
                INSERT INTO episode_lifecycle_events (
                    episode_id, event_type, reason_code, manifest_id
                )
                VALUES ($1, 'activated', 'manifest_created', $2)
                """,
                episode_id,
                manifest_id,
            )
        elif previous["retired_at"] is not None:
            activated += 1
            await connection.execute(
                """
                INSERT INTO episode_lifecycle_events (
                    episode_id, event_type, reason_code, manifest_id
                )
                VALUES ($1, 'activated', 'manifest_reactivated', $2)
                """,
                episode_id,
                manifest_id,
            )

    retired_rows = await connection.fetch(
        """
        UPDATE episodes
        SET retired_at = clock_timestamp(),
            retirement_reason_code = 'not_in_active_manifest',
            embedding = NULL,
            updated_at = clock_timestamp()
        WHERE document_id = $1
          AND retired_at IS NULL
          AND episode_index >= $2
        RETURNING id
        """,
        document_id,
        len(manifest.items),
    )
    for row in retired_rows:
        await connection.execute(
            """
            INSERT INTO episode_lifecycle_events (
                episode_id, event_type, reason_code, manifest_id
            )
            VALUES ($1, 'retired', 'not_in_active_manifest', $2)
            """,
            row["id"],
            manifest_id,
        )

    await connection.execute(
        """
        UPDATE lore_documents
        SET active_chunk_manifest_id = $2,
            processing_status = 'completed',
            processed_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
        """,
        document_id,
        manifest_id,
    )
    active_count = int(
        await connection.fetchval(
            """
            SELECT count(*)
            FROM episodes
            WHERE document_id = $1 AND retired_at IS NULL
            """,
            document_id,
        )
    )
    if active_count != len(manifest.items):
        raise RuntimeError("Active episode count does not match the chunk manifest")
    return {
        "manifest_fingerprint": manifest.fingerprint,
        "active": active_count,
        "created": created,
        "reactivated": activated,
        "retired": len(retired_rows),
    }
