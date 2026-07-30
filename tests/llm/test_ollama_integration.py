"""Integration tests for Ollama provider."""

import pytest

from src.llm.providers.ollama_provider import OllamaProvider


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_generate():
    """Test Ollama generation."""
    provider = OllamaProvider()

    response = await provider.generate("Write one sentence about crystal dwarves.", temperature=0.7)

    assert isinstance(response, str)
    assert len(response) > 0
    print(f"Generated: {response}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_stream():
    """Test Ollama streaming."""
    provider = OllamaProvider()

    chunks = []
    async for chunk in provider.stream("Say hello.", temperature=0.7):
        chunks.append(chunk)

    assert len(chunks) > 0
    full_response = "".join(chunks)
    print(f"Streamed: {full_response}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_embed():
    """Test Ollama embeddings."""
    provider = OllamaProvider()

    # Single embedding
    embedding = await provider.embed("test text")
    assert isinstance(embedding, list)
    assert len(embedding) == 768  # nomic-embed-text dimension

    # Batch embedding
    embeddings = await provider.embed(["text1", "text2"])
    assert len(embeddings) == 2
    assert all(len(emb) == 768 for emb in embeddings)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_generate_with_custom_model():
    """Test Ollama generation with custom model."""
    provider = OllamaProvider()

    response = await provider.generate("Write one word.", model="qwen2.5:7b", temperature=0.3)

    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_generate_with_max_tokens():
    """Test Ollama generation with max tokens limit."""
    provider = OllamaProvider()

    response = await provider.generate(
        "Tell me a story about dwarves.", temperature=0.7, max_tokens=50
    )

    assert isinstance(response, str)
    assert len(response) > 0
    # Note: Token count is approximate, just verify it's not too long
    assert len(response.split()) < 100  # Rough token approximation


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_stream_multiple_chunks():
    """Test Ollama streaming returns multiple chunks."""
    provider = OllamaProvider()

    chunks = []
    async for chunk in provider.stream("Count to five.", temperature=0.7):
        chunks.append(chunk)

    # Should have received multiple chunks for this response
    assert len(chunks) > 1
    full_response = "".join(chunks)
    assert len(full_response) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_embed_batch_processing():
    """Test Ollama batch embedding processing."""
    provider = OllamaProvider()

    texts = [
        "The crystal dwarves live in mountains.",
        "They are masters of mining.",
        "Their craftsmanship is legendary.",
    ]

    embeddings = await provider.embed(texts)

    assert len(embeddings) == len(texts)
    for emb in embeddings:
        assert isinstance(emb, list)
        assert len(emb) == 768
        # Verify embeddings have non-zero values
        assert any(val != 0 for val in emb)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_provider_model_info():
    """Test Ollama provider returns correct model info."""
    provider = OllamaProvider()

    info = provider.get_model_info()

    assert info["provider"] == "ollama"
    assert "chat_model" in info
    assert "creative_model" in info
    assert "reasoning_model" in info
    assert "embedding_model" in info
    assert "base_url" in info
    assert "max_context_tokens" in info
