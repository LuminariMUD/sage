"""Tests for deterministic chunk manifests and content-role policy."""

import pytest

from src.ingestion.chunk_manifest import (
    RUNTIME_CONTRACT,
    WORLD_LORE,
    ChunkingProfile,
    build_chunk_manifest,
    resolve_content_role_policy,
)


def _profile(*, policy: str = "include_all_v1") -> ChunkingProfile:
    return ChunkingProfile(
        base_tokens=200,
        min_tokens=100,
        max_tokens=500,
        overlap_percentage=0.25,
        similarity_threshold=0.7,
        complexity_factor=1.5,
        embedding_model="embedding-model",
        embedding_revision="revision-1",
        tokenizer="tokenizer-v1",
        sentence_segmenter="segmenter-v1",
        content_role_policy=policy,
    )


def test_manifest_fingerprints_are_content_addressed_and_profile_versioned():
    chunks = [{"text": "Lumia rests beneath a silver sky."}]
    first = build_chunk_manifest("# Lumia\n\n" + chunks[0]["text"], chunks, _profile())
    repeated = build_chunk_manifest("# Lumia\n\n" + chunks[0]["text"], chunks, _profile())
    excluded = build_chunk_manifest(
        "# Lumia\n\n" + chunks[0]["text"],
        chunks,
        _profile(policy="exclude_non_lore_v1"),
    )

    assert first.fingerprint == repeated.fingerprint
    assert first.profile.fingerprint == repeated.profile.fingerprint
    assert first.fingerprint != excluded.fingerprint
    assert first.profile.fingerprint != excluded.profile.fingerprint


def test_exclusion_policy_keeps_runtime_guidance_retrievable_but_not_graph_eligible():
    document = """# The Silver Road

The Silver Road crosses Lumia beneath the moon.

## Runtime Integration Contract

The runtime stable ID and media key are database field contracts.
"""
    manifest = build_chunk_manifest(
        document,
        [
            {"text": "The Silver Road crosses Lumia beneath the moon."},
            {
                "text": (
                    "The runtime stable ID and media key are database field contracts."
                )
            },
        ],
        _profile(policy="exclude_non_lore_v1"),
    )

    assert manifest.items[0].content_role == WORLD_LORE
    assert manifest.items[0].graph_extraction_eligible is True
    assert manifest.items[1].content_role == RUNTIME_CONTRACT
    assert manifest.items[1].graph_extraction_eligible is False
    assert manifest.items[1].text


def test_invalid_policy_and_chunk_contract_fail_closed():
    with pytest.raises(ValueError, match="unsupported"):
        resolve_content_role_policy("unknown")
    with pytest.raises(ValueError, match="text is missing"):
        build_chunk_manifest("# Lore", [{"text": ""}], _profile())
