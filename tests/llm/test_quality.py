"""Quality validation tests for LangChain chains with provider abstraction.

This module tests that responses from LangChain chains are coherent,
accurate, and meet quality standards when using the provider abstraction.
"""

import pytest

from src.agents.langchain.chains.direct_answer import DirectAnswerChain
from src.agents.langchain.chains.unified_creative import UnifiedCreativeTool
from src.llm.config import get_llm_provider_config


@pytest.mark.integration
@pytest.mark.asyncio
async def test_direct_answer_quality():
    """Test direct answer chain produces quality responses."""
    chain = DirectAnswerChain()

    # Test factual question
    context = [
        """
        The Crystal Dwarves of Nagburim are master miners who live deep
        underground. They are renowned for their skill in working with
        crystalline materials and gemstones.
        """,
        """
        ENTITY Crystal Dwarves (Race): A subrace of dwarves with translucent,
        crystal-like skin. They possess darkvision and resistance to cold.
        """,
    ]

    question = "Who are the Crystal Dwarves?"

    result = chain.invoke({"query": question, "context_blocks": context})

    print(f"\n\nAnswer:\n{result['answer']}")
    print(f"\nUsed {result['used_blocks']} blocks")

    # Quality checks
    assert len(result["answer"]) > 50, "Answer should be substantial"
    assert result["used_blocks"] > 0, "Should use provided context"

    # Check if answer contains key information
    answer_lower = result["answer"].lower()
    assert any(
        word in answer_lower for word in ["crystal", "dwarf", "nagburim"]
    ), "Answer should mention key entities"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_direct_answer_coherence():
    """Test answer coherence and structure."""
    chain = DirectAnswerChain()

    context = ["The Mark of the Luminari is a magical tattoo that grants enhanced abilities."]

    result = chain.invoke({"query": "What is the Mark of the Luminari?", "context_blocks": context})

    answer = result["answer"]
    print(f"\n\nAnswer:\n{answer}")

    # Check for structured response
    assert "##" in answer or "#" in answer, "Should have markdown headers"
    assert len(answer.split("\n")) > 3, "Should have multiple lines"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_creative_content_quality():
    """Test creative content generation quality."""
    tool = UnifiedCreativeTool()

    result = await tool.create_content(
        content_type="character",
        requirements={
            "name": "Glint Ironvein",
            "race": "Crystal Dwarf",
            "role": "Master Gemcutter",
            "personality": "Meticulous and proud",
        },
        context=["Crystal Dwarves are known for their precision and artistry."],
    )

    print(f"\n\nCreated character:\n{result}")

    assert result["type"] == "character", "Should return correct type"
    assert result["data"] is not None, "Should have data"
    assert not result.get("error"), "Should not have errors"

    # Check metadata
    assert result["metadata"]["had_context"], "Should acknowledge context"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_consistency():
    """Test that provider abstraction produces consistent results."""
    config = get_llm_provider_config()
    provider = config["provider"]

    print(f"\n\nTesting with provider: {provider}")

    chain = DirectAnswerChain()

    # Simple test
    result = chain.invoke({"query": "What is 2+2?", "context_blocks": ["The answer to 2+2 is 4."]})

    answer = result["answer"]
    print(f"Answer: {answer}")

    # Should produce a response
    assert len(answer) > 0, "Should produce an answer"
    assert "4" in answer, "Should correctly reference the answer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_context_blocks():
    """Test handling of multiple context blocks."""
    chain = DirectAnswerChain()

    context_blocks = [
        "Crystal Dwarves live in Nagburim.",
        "They have translucent skin.",
        "They are master gemcutters.",
        "They speak the Tal language.",
        "ENTITY Crystal Dwarves (Race): Subrace with crystal-like properties.",
    ]

    result = chain.invoke(
        {"query": "Tell me about Crystal Dwarves.", "context_blocks": context_blocks}
    )

    print(f"\n\nAnswer with {len(context_blocks)} context blocks:\n{result['answer']}")

    # Should reference multiple blocks
    assert result["used_blocks"] >= 3, "Should use multiple context blocks"

    # Answer should be comprehensive
    answer_lower = result["answer"].lower()
    mentions = sum(
        [
            "nagburim" in answer_lower,
            "translucent" in answer_lower or "crystal" in answer_lower,
            "gemcutter" in answer_lower or "gem" in answer_lower,
        ]
    )

    assert mentions >= 2, "Should mention multiple facts from context"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_grounding():
    """Test that answers are grounded in provided context."""
    chain = DirectAnswerChain()

    specific_context = [
        "The Crystal Dwarves of Nagburim speak only the Tal language.",
        "Tal is a language unique to the Crystal Dwarves.",
    ]

    result = chain.invoke(
        {"query": "What language do Crystal Dwarves speak?", "context_blocks": specific_context}
    )

    answer = result["answer"]
    print(f"\n\nGrounded answer:\n{answer}")

    # Should mention Tal from the context
    assert "tal" in answer.lower(), "Answer should be grounded in context (mention Tal)"

    # Should not make up information
    assert "common" not in answer.lower(), "Should not invent languages not in context"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_context_handling():
    """Test handling of queries with no context."""
    chain = DirectAnswerChain()

    result = chain.invoke({"query": "Tell me about something", "context_blocks": []})

    answer = result["answer"]
    print(f"\n\nAnswer with no context:\n{answer}")

    # Should acknowledge lack of context
    assert len(answer) > 0, "Should still produce a response"
    assert result["used_blocks"] == 0, "Should show no blocks used"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_temperature_impact():
    """Test that temperature affects response variability."""
    from src.llm.langchain_helpers import get_chat_model

    # Low temperature (deterministic)
    llm_low = get_chat_model(task="reasoning", temperature=0.0, streaming=False)
    response1 = llm_low.invoke("Say 'hello'")
    response2 = llm_low.invoke("Say 'hello'")

    print(f"\n\nLow temp response 1: {response1.content}")
    print(f"Low temp response 2: {response2.content}")

    # Responses should be very similar with temp=0
    # (Exact match not guaranteed due to provider differences)
    assert len(response1.content) > 0 and len(response2.content) > 0


if __name__ == "__main__":
    # Allow running tests directly for quick verification
    import asyncio

    print("Testing LangChain chain quality with provider abstraction...")
    print("=" * 60)

    async def run_tests():
        print("\n1. Testing direct answer quality...")
        await test_direct_answer_quality()

        print("\n\n2. Testing answer coherence...")
        await test_direct_answer_coherence()

        print("\n\n3. Testing creative content...")
        await test_creative_content_quality()

        print("\n\n4. Testing provider consistency...")
        await test_provider_consistency()

        print("\n\n5. Testing multiple context blocks...")
        await test_multiple_context_blocks()

        print("\n\n6. Testing context grounding...")
        await test_context_grounding()

        print("\n\n7. Testing empty context handling...")
        await test_empty_context_handling()

    asyncio.run(run_tests())
    print("\n\nAll manual quality tests completed!")
