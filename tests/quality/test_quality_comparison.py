"""Quality comparison: Ollama vs OpenAI."""

import os

import pytest

from src.llm.providers.factory import get_llm_provider, reset_provider_cache

TEST_QUERIES = [
    ("Who are the Crystal Dwarves?", ["crystal", "dwarf", "nagburim"]),
    ("Describe a magical crystal.", ["magic", "crystal", "power"]),
    ("What races live in LuminariMUD?", ["race", "character", "world"]),
]


@pytest.mark.quality
@pytest.mark.integration
@pytest.mark.asyncio
async def test_compare_providers():
    """Compare response quality between providers."""
    results = {"ollama": [], "openai": []}

    for provider_name in ["ollama", "openai"]:
        if provider_name == "openai" and not os.getenv("OPENAI_API_KEY"):
            print("\n⏭️  Skipping OpenAI tests (no API key)")
            continue

        print(f"\n\n{'='*60}")
        print(f"Testing provider: {provider_name.upper()}")
        print("=" * 60)

        # Configure provider
        os.environ["LLM_PROVIDER"] = provider_name
        reset_provider_cache()
        provider = get_llm_provider()

        for query, expected_keywords in TEST_QUERIES:
            print(f"\n❓ Query: {query}")

            response = await provider.generate(query, temperature=0.7)
            response_lower = response.lower()

            # Check keyword presence
            found_keywords = [kw for kw in expected_keywords if kw in response_lower]
            quality_score = len(found_keywords) / len(expected_keywords)

            results[provider_name].append(
                {
                    "query": query,
                    "response": response,
                    "keywords_found": found_keywords,
                    "quality_score": quality_score,
                }
            )

            print(f"✅ Response: {response[:100]}...")
            print(f"📊 Quality: {quality_score*100:.0f}% (keywords: {found_keywords})")

    # Compare results
    if results["openai"]:
        print(f"\n\n{'='*60}")
        print("COMPARISON SUMMARY")
        print("=" * 60)

        ollama_avg = sum(r["quality_score"] for r in results["ollama"]) / len(results["ollama"])
        openai_avg = sum(r["quality_score"] for r in results["openai"]) / len(results["openai"])

        print(f"\nOllama average quality: {ollama_avg*100:.1f}%")
        print(f"OpenAI average quality: {openai_avg*100:.1f}%")
        print(f"Ollama relative to OpenAI: {(ollama_avg/openai_avg)*100:.1f}%")

        # Quality should be at least 70% of OpenAI
        assert ollama_avg >= 0.7 * openai_avg, "Ollama quality below 70% of OpenAI"
    else:
        print("\n⚠️  Skipped comparison (OpenAI not available)")
        # Just verify Ollama works
        assert len(results["ollama"]) > 0, "Should have Ollama results"
        ollama_avg = sum(r["quality_score"] for r in results["ollama"]) / len(results["ollama"])
        print(f"\nOllama standalone quality: {ollama_avg*100:.1f}%")
        # Ollama should still produce reasonable results
        assert ollama_avg >= 0.5, "Ollama should score at least 50% on keyword matching"


@pytest.mark.quality
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_response_coherence():
    """Test Ollama produces coherent responses."""
    os.environ["LLM_PROVIDER"] = "ollama"
    reset_provider_cache()
    provider = get_llm_provider()

    print(f"\n\n{'='*60}")
    print("Testing Ollama Response Coherence")
    print("=" * 60)

    test_prompts = [
        "Explain what makes crystal dwarves unique in one paragraph.",
        "Write three bullet points about mining safety.",
        "Describe a crystal cave in two sentences.",
    ]

    for prompt in test_prompts:
        print(f"\n📝 Prompt: {prompt}")

        response = await provider.generate(prompt, temperature=0.7)

        print(f"✅ Response ({len(response)} chars): {response[:150]}...")

        # Basic coherence checks
        assert len(response) > 20, "Response should be substantial"
        assert len(response) < 2000, "Response should be concise"

        # Check for common coherence markers
        has_structure = any(
            [
                "\n" in response,  # Line breaks
                "." in response,  # Sentences
                "," in response,  # Clauses
            ]
        )
        assert has_structure, "Response should have basic structure"


@pytest.mark.quality
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_factual_accuracy():
    """Test Ollama maintains factual accuracy with context."""
    os.environ["LLM_PROVIDER"] = "ollama"
    reset_provider_cache()
    provider = get_llm_provider()

    print(f"\n\n{'='*60}")
    print("Testing Ollama Factual Accuracy")
    print("=" * 60)

    # Test with a factual prompt
    prompt = "Based on this context: 'The Crystal Dwarves live in Nagburim and mine crystals.' Where do Crystal Dwarves live?"

    response = await provider.generate(prompt, temperature=0.3)  # Low temp for accuracy

    print(f"\n❓ Question: {prompt}")
    print(f"✅ Response: {response}")

    response_lower = response.lower()

    # Should mention Nagburim
    assert "nagburim" in response_lower, "Should correctly identify Nagburim"

    print("\n✅ Factual accuracy maintained!")


@pytest.mark.quality
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_creative_quality():
    """Test Ollama creative generation quality."""
    os.environ["LLM_PROVIDER"] = "ollama"
    reset_provider_cache()
    provider = get_llm_provider()

    print(f"\n\n{'='*60}")
    print("Testing Ollama Creative Quality")
    print("=" * 60)

    creative_prompts = [
        "Write a haiku about crystal mining.",
        "Create a name for a legendary crystal sword.",
        "Describe the sound of crystals resonating in a cave.",
    ]

    for prompt in creative_prompts:
        print(f"\n🎨 Prompt: {prompt}")

        response = await provider.generate(prompt, temperature=0.9)  # High temp for creativity

        print(f"✨ Response: {response}")

        # Basic quality checks
        assert len(response) > 10, "Creative response should have content"
        assert not response.startswith("I cannot") and not response.startswith(
            "I can't"
        ), "Should attempt creative generation"


@pytest.mark.quality
@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_consistency():
    """Test provider produces consistent results with same input."""
    os.environ["LLM_PROVIDER"] = "ollama"
    reset_provider_cache()
    provider = get_llm_provider()

    print(f"\n\n{'='*60}")
    print("Testing Provider Consistency")
    print("=" * 60)

    prompt = "What is 2 + 2?"

    # Run same prompt multiple times with low temperature
    responses = []
    for i in range(3):
        response = await provider.generate(prompt, temperature=0.0)
        responses.append(response)
        print(f"\n   Run {i+1}: {response[:50]}...")

    # All responses should mention 4
    for response in responses:
        assert "4" in response or "four" in response.lower(), "Should consistently answer 2+2=4"

    print("\n✅ Provider shows consistent behavior!")


@pytest.mark.quality
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_embedding_quality():
    """Test Ollama embedding quality."""
    os.environ["LLM_PROVIDER"] = "ollama"
    reset_provider_cache()
    provider = get_llm_provider()

    print(f"\n\n{'='*60}")
    print("Testing Ollama Embedding Quality")
    print("=" * 60)

    # Test similar texts should have similar embeddings
    text1 = "The Crystal Dwarves mine precious gems"
    text2 = "Crystal Dwarves are expert miners of gemstones"
    text3 = "Elves live in ancient forests"

    emb1 = await provider.embed(text1)
    emb2 = await provider.embed(text2)
    emb3 = await provider.embed(text3)

    print(f"\n📊 Embedding dimensions: {len(emb1)}")

    # Calculate cosine similarity
    import math

    def cosine_similarity(a, b):
        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = math.sqrt(sum(x * x for x in a))
        magnitude_b = math.sqrt(sum(y * y for y in b))
        return dot_product / (magnitude_a * magnitude_b)

    sim_1_2 = cosine_similarity(emb1, emb2)
    sim_1_3 = cosine_similarity(emb1, emb3)

    print(f"   Similarity (text1 <-> text2): {sim_1_2:.3f}")
    print(f"   Similarity (text1 <-> text3): {sim_1_3:.3f}")

    # Similar texts should have higher similarity than dissimilar texts
    assert sim_1_2 > sim_1_3, "Similar texts should have higher similarity"
    assert sim_1_2 > 0.5, "Similar texts should have meaningful similarity"

    print("\n✅ Embedding quality verified!")


if __name__ == "__main__":
    # Allow running tests directly for quick verification
    import asyncio

    async def run_all():
        print("Running quality comparison tests...")
        await test_compare_providers()
        await test_ollama_response_coherence()
        await test_ollama_factual_accuracy()
        await test_ollama_creative_quality()
        await test_provider_consistency()
        await test_ollama_embedding_quality()

    asyncio.run(run_all())
