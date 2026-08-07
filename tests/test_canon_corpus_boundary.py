"""Regression coverage for the fail-closed canon corpus boundary."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.scripts import create_episodes_from_documents, generate_embeddings
from src.scripts.load_documents import DocumentLoader
from src.scripts.sync_episodes_to_graphiti import (
    CanonCorpusViolation,
    require_canon_episode_corpus,
)


def test_document_loader_accepts_only_canon_source(tmp_path):
    (tmp_path / "canon").mkdir()

    with pytest.raises(ValueError, match="restricted to lore_docs/canon"):
        DocumentLoader(str(tmp_path), source="draft")

    with pytest.raises(ValueError, match="restricted to lore_docs/canon"):
        DocumentLoader(str(tmp_path), source="all")


def test_document_loader_scans_only_canon_and_rejects_direct_draft_paths(tmp_path):
    canon_file = tmp_path / "canon" / "world" / "truth.md"
    draft_file = tmp_path / "drafts" / "world" / "noise.md"
    canon_file.parent.mkdir(parents=True)
    draft_file.parent.mkdir(parents=True)
    canon_file.write_text("# Truth\n", encoding="utf-8")
    draft_file.write_text("# Noise\n", encoding="utf-8")
    loader = DocumentLoader(str(tmp_path))

    assert loader.find_markdown_files() == [canon_file]
    assert loader.canon_relative_path(canon_file) == Path("canon/world/truth.md")
    with pytest.raises(ValueError, match="outside lore_docs/canon"):
        loader.canon_relative_path(draft_file)


def test_document_loader_rejects_symlinks_that_escape_canon(tmp_path):
    canon_dir = tmp_path / "canon"
    draft_file = tmp_path / "drafts" / "noise.md"
    canon_dir.mkdir()
    draft_file.parent.mkdir()
    draft_file.write_text("# Noise\n", encoding="utf-8")
    (canon_dir / "escape.md").symlink_to(draft_file)

    with pytest.raises(ValueError, match="outside lore_docs/canon"):
        DocumentLoader(str(tmp_path)).find_markdown_files()


async def test_episode_creation_selects_and_resets_only_canon_documents():
    database = SimpleNamespace(
        execute=AsyncMock(),
        fetch=AsyncMock(return_value=[]),
        disconnect=AsyncMock(),
    )

    with (
        patch.object(
            create_episodes_from_documents,
            "get_postgres_db",
            AsyncMock(return_value=database),
        ),
        patch.object(create_episodes_from_documents, "EpisodeCreator", return_value=object()),
    ):
        assert await create_episodes_from_documents.create_episodes_from_documents(
            force_recreate=True
        )

    reset_query = database.execute.await_args_list[0].args[0]
    selection_query = database.fetch.await_args.args[0]
    for query in (reset_query, selection_query):
        assert "canonical IS TRUE" in query
        assert "source_file LIKE 'canon/%'" in query


async def test_embedding_generation_fetches_only_canon_episodes():
    database = SimpleNamespace(fetch=AsyncMock(return_value=[]))
    embedder = SimpleNamespace(get_dimension=lambda: 768)

    with patch.object(
        generate_embeddings,
        "preflight_embedding_space",
        AsyncMock(return_value={"ready": True}),
    ):
        await generate_embeddings.generate_embeddings(
            database_getter=AsyncMock(return_value=database),
            profile_resolver=lambda: SimpleNamespace(dimensions=768),
            embedder_factory=lambda **_kwargs: embedder,
        )

    query = database.fetch.await_args.args[0]
    assert "JOIN lore_documents" in query
    assert "document.canonical IS TRUE" in query
    assert "document.source_file LIKE 'canon/%'" in query


async def test_graph_sync_rejects_excluded_episodes_before_provider_access():
    database = SimpleNamespace(fetchval=AsyncMock(return_value=1))

    with pytest.raises(CanonCorpusViolation, match="outside lore_docs/canon"):
        await require_canon_episode_corpus(database)

    query = database.fetchval.await_args.args[0]
    assert "document.canonical IS NOT TRUE" in query
    assert "NOT LIKE 'canon/%'" in query


def test_makefile_retires_draft_and_all_pipeline_targets():
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")

    assert "--source draft" not in makefile
    assert "--source all" not in makefile
    assert "load-draft load-all:" in makefile
    assert "pipeline-draft pipeline-all:" in makefile
    assert makefile.count("This pipeline is canon-only") == 2
    assert "pipeline-canon: db-migrate-check load-canon" in makefile
    assert "resume: db-migrate-check" in makefile


def test_compose_mounts_expose_only_the_canon_directory():
    repository = Path(__file__).resolve().parents[1]
    development = (repository / "docker-compose.yml").read_text(encoding="utf-8")
    production = (repository / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "./lore_docs/canon:/app/lore_docs/canon:ro" in development
    assert "./lore_docs:/app/lore_docs:ro" not in development
    assert "/lore_docs/canon:/app/lore/lore_docs/canon:ro" in production
    assert "/lore_docs:/app/lore/lore_docs:ro" not in production
    assert "LORE_SOURCE:" not in development
    assert "LORE_SOURCE:" not in production


def test_rag_queries_have_a_canon_source_boundary():
    api_source = (Path(__file__).resolve().parents[1] / "src" / "api" / "main.py").read_text(
        encoding="utf-8"
    )

    assert api_source.count("source_file LIKE 'canon/%'") >= 7
    assert "canonical_only: bool = Query(False" not in api_source
