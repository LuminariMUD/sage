"""Test script for reflection functionality in LangChain chat agent.

Tests:
1. Fact-checking against context
2. Context insufficiency detection
3. Re-retrieval on missing information
4. Plan validation for orchestrator
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.langchain.chains.reflection import ReflectionChain
from src.agents.langchain.service import LangChainChatService

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Test queries that should trigger different reflection behaviors
TEST_QUERIES = [
    {
        "query": "What is the complete timeline from the Age of Titans through the Age of Mortals, including all major events?",
        "expected_behavior": "Should detect need for more timeline context",
        "type": "complex_timeline",
    },
    {
        "query": "Explain the relationship between the Prisoner and the Five Locks, and how they were created.",
        "expected_behavior": "Should request additional context about both entities",
        "type": "relationship_query",
    },
    {
        "query": "Tell me about Crystal Dwarves and their reincarnation process in detail.",
        "expected_behavior": "Should gather comprehensive information about Crystal Dwarves",
        "type": "detailed_lore",
    },
    {
        "query": "Create a story about a new character discovering ancient ruins, then plan a quest based on that story.",
        "expected_behavior": "Should validate multi-step orchestration plan",
        "type": "orchestrated",
    },
]


async def test_reflection_on_answer():
    """Test reflection on a simple answer."""
    print("\n=== Testing Reflection on Answer ===")

    reflection = ReflectionChain()

    # Test with insufficient context
    result = await reflection.reflect_on_answer(
        answer="The Prisoner was locked away using the Five Locks created by the ancient mages in the year 1234.",
        question="How was the Prisoner imprisoned?",
        context_blocks=["The Prisoner is an ancient entity of great power."],
    )

    print(f"Is grounded: {result.is_grounded}")
    print(f"Context sufficient: {result.context_sufficient}")
    print(f"Unsupported claims: {result.unsupported_claims}")
    print(f"Suggested queries: {result.suggested_queries}")
    print(f"Confidence: {result.confidence_score}")

    # Test with good context
    result2 = await reflection.reflect_on_answer(
        answer="The Prisoner is an ancient entity of immense power.",
        question="What is the Prisoner?",
        context_blocks=[
            "The Prisoner is an ancient entity of great power.",
            "The Prisoner was imprisoned long ago.",
        ],
    )

    print("\nWith good context:")
    print(f"Is grounded: {result2.is_grounded}")
    print(f"Confidence: {result2.confidence_score}")


async def test_chat_with_reflection():
    """Test the full chat service with reflection enabled."""
    print("\n=== Testing Chat Service with Reflection ===")

    # Initialize service with reflection
    service = LangChainChatService(enable_reflection=True)

    for test_case in TEST_QUERIES[:2]:  # Test first two queries
        print(f"\n--- Testing: {test_case['type']} ---")
        print(f"Query: {test_case['query']}")
        print(f"Expected: {test_case['expected_behavior']}")

        try:
            result = await service.chat(test_case["query"])

            print(f"Route: {result.get('route')}")
            print(f"Reflection applied: {result.get('reflection_applied', False)}")
            print(f"Additional retrieval: {result.get('additional_retrieval', 0)}")
            print(f"Confidence: {result.get('confidence_score', 'N/A')}")
            print(f"Answer preview: {result.get('answer', '')[:200]}...")

        except Exception as e:
            print(f"Error: {e}")


async def test_plan_validation():
    """Test plan validation in orchestrator."""
    print("\n=== Testing Plan Validation ===")

    reflection = ReflectionChain()

    # Test a complex plan
    plan = {
        "user_intent": "Create story then quest",
        "needs_orchestration": True,
        "execution_plan": [
            {
                "step": 1,
                "tool": "search_lore",
                "description": "Search for lore context",
                "input": {"query": "ancient ruins"},
                "output_key": "lore",
            },
            {
                "step": 2,
                "tool": "develop_story",
                "description": "Create story",
                "input": {"prompt": "story about ruins", "previous_context": "{{step_1}}"},
                "output_key": "story",
            },
            {
                "step": 3,
                "tool": "plan_quest",
                "description": "Plan quest from story",
                "input": {"premise": "quest from story", "previous_context": "{{step_2}}"},
                "output_key": "quest",
            },
        ],
    }

    result = await reflection.reflect_on_plan(
        plan=plan,
        request="Create a story about discovering ancient ruins, then make a quest based on it",
    )

    print(f"Plan valid: {result.plan_valid}")
    print(f"Issues: {result.issues}")
    print(f"Suggestions: {result.suggestions}")
    print(f"Confidence: {result.confidence_score}")


async def main():
    """Run all reflection tests."""
    print("Starting Reflection Tests")
    print("=" * 50)

    # Check if OpenAI API key is configured
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Reflection will be disabled.")
        print("Set the environment variable to test full functionality.")

    await test_reflection_on_answer()
    await test_chat_with_reflection()
    await test_plan_validation()

    print("\n" + "=" * 50)
    print("Reflection Tests Complete")


if __name__ == "__main__":
    asyncio.run(main())
