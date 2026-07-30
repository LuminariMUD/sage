"""Test that reflection catches factual errors using context, not hardcoded rules.

This test verifies that the system can detect misattributions (like elves speaking Tal)
by checking against the knowledge base context, without any hardcoded lore facts.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.langchain.chains.reflection import ReflectionChain


async def test_tal_misattribution():
    """Test that reflection catches Tal language misattribution using context."""
    print("Testing context-based error detection for Tal language...")

    reflection = ReflectionChain()

    # Context that clearly states Tal is Crystal Dwarves' language
    context_blocks = [
        "Crystal Dwarves speak in Tal, a language of harmonic resonance that sounds like living music.",
        "Elves emerged from moonlight and memory, with pointed ears attuned to the Otherworld.",
        "The Crystal Dwarves of Nagburim communicate through vibrations and musical tones.",
    ]

    # Answer that incorrectly attributes Tal to elves
    incorrect_answer = (
        "The elves speak in Tal, their voices resonating like symphonies through crystalline halls."
    )

    result = await reflection.reflect_on_answer(
        answer=incorrect_answer,
        question="Tell me about elven language",
        context_blocks=context_blocks,
    )

    print("\nResults for incorrect Tal attribution:")
    print(f"- Is grounded: {result.is_grounded}")
    print(f"- Unsupported claims: {result.unsupported_claims}")
    print(f"- Confidence: {result.confidence_score}")
    print(f"- Reasoning: {result.reasoning}")

    # The system should detect this as unsupported because:
    # 1. Context says Crystal Dwarves speak Tal
    # 2. Context doesn't say elves speak Tal
    # 3. Therefore attributing Tal to elves is unsupported

    assert not result.is_grounded, "Should detect the answer is not grounded"
    assert result.confidence_score < 0.7, "Should have low confidence"
    assert any(
        "tal" in claim.lower() or "elves speak" in claim.lower()
        for claim in result.unsupported_claims
    ), "Should identify Tal/elves claim as unsupported"

    print("\n✓ Successfully detected misattribution through context analysis")


async def test_correct_attribution():
    """Test that reflection approves correct attributions."""
    print("\nTesting correct attribution...")

    reflection = ReflectionChain()

    context_blocks = [
        "Crystal Dwarves speak in Tal, a language of harmonic resonance that sounds like living music.",
        "They communicate through vibrations and musical tones that ring through crystal halls.",
    ]

    # Correct answer about Crystal Dwarves and Tal
    correct_answer = "The Crystal Dwarves communicate in Tal, a harmonic language that resonates through their crystalline halls like living music."

    result = await reflection.reflect_on_answer(
        answer=correct_answer,
        question="How do Crystal Dwarves communicate?",
        context_blocks=context_blocks,
    )

    print("\nResults for correct attribution:")
    print(f"- Is grounded: {result.is_grounded}")
    print(f"- Unsupported claims: {result.unsupported_claims}")
    print(f"- Confidence: {result.confidence_score}")

    assert result.is_grounded, "Should recognize correct attribution as grounded"
    assert result.confidence_score > 0.7, "Should have high confidence"

    print("\n✓ Successfully approved correct attribution")


async def test_missing_context():
    """Test that reflection requests more context when information is missing."""
    print("\nTesting missing context detection...")

    reflection = ReflectionChain()

    # Limited context - doesn't mention elven language at all
    context_blocks = [
        "Elves are an ancient race with pointed ears.",
        "They emerged from moonlight and memory.",
    ]

    # Answer makes claims about elven language
    answer = "Elves speak an ancient melodic language passed down through generations."

    result = await reflection.reflect_on_answer(
        answer=answer, question="What language do elves speak?", context_blocks=context_blocks
    )

    print("\nResults for missing context:")
    print(f"- Context sufficient: {result.context_sufficient}")
    print(f"- Missing aspects: {result.missing_aspects}")
    print(f"- Suggested queries: {result.suggested_queries}")

    assert not result.context_sufficient, "Should detect insufficient context"
    assert result.suggested_queries, "Should suggest queries for more information"

    print("\n✓ Successfully identified need for additional context")


async def main():
    """Run all context-based reflection tests."""
    print("=" * 60)
    print("Context-Based Reflection Tests")
    print("=" * 60)

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Tests will use fallback behavior.")
        print("Set the environment variable for full testing.\n")

    try:
        await test_tal_misattribution()
        await test_correct_attribution()
        await test_missing_context()

        print("\n" + "=" * 60)
        print("✅ All context-based reflection tests passed!")
        print("The system correctly detects errors using context alone,")
        print("without any hardcoded lore facts.")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        print("The system may need adjustment to better detect")
        print("misattributions through context analysis.")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
