"""Deterministic local-model configuration for semantic chunking."""

from types import SimpleNamespace

from src.scripts import semantic_chunker


def test_semantic_chunker_uses_pinned_environment_revision(monkeypatch):
    captured = {}

    def fake_sentence_transformer(model, **kwargs):
        captured["model"] = model
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("SAGE_SENTENCE_TRANSFORMERS_REVISION", "pinned-revision")
    monkeypatch.setattr(semantic_chunker, "SentenceTransformer", fake_sentence_transformer)
    monkeypatch.setattr(
        semantic_chunker.spacy,
        "load",
        lambda model: SimpleNamespace(model=model),
    )

    semantic_chunker.SemanticChunker()

    assert captured == {
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "pinned-revision",
    }
