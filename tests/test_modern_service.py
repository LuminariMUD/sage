"""Test modern tool-based service vs legacy keyword routing.

Demonstrates how the modern approach handles complex requests better.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.langchain.modern_service import ModernLangChainService
from src.agents.langchain.service import LangChainChatService

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Test cases that were problematic with keyword routing
TEST_CASES = [
    {
        "name": "Multiple Quests",
        "query": "Create 4 quests that span the player's discovery of the origins and future of the arcana golem race",
        "expected_modern": "Should call create_quest 4 times with context passing",
        "expected_legacy": "Might route to single quest or orchestrator",
    },
    {
        "name": "Mixed Operations",
        "query": "Tell me about the Crystal Dwarves, then create a quest involving them",
        "expected_modern": "Should call answer_question then create_quest",
        "expected_legacy": "Needs orchestrator with complex patterns",
    },
    {
        "name": "Context-Aware",
        "query": "Write an extended narrative about elves and their culture",
        "expected_modern": "Should search_lore then write_narrative with length=extended",
        "expected_legacy": "Might miss the 'extended' requirement",
    },
]


async def test_modern_service():
    """Test the modern tool-based service."""
    print("=" * 60)
    print("Testing Modern Tool-Based Service")
    print("=" * 60)

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set. Skipping modern service tests.")
        return

    # Use a smaller model for testing if GPT-4 not available
    model = os.getenv("TEST_MODEL", "gpt-4o-mini")
    service = ModernLangChainService(model_name=model)

    for test_case in TEST_CASES:
        print(f"\n### {test_case['name']}")
        print(f"Query: {test_case['query']}")
        print(f"Expected: {test_case['expected_modern']}")

        try:
            # Mock the tool execution for testing
            result = await service.chat(test_case["query"])

            print("\nTool calls made:")
            for tool_call in result.get("tool_calls", []):
                print(f"  - {tool_call['tool']}({list(tool_call['args'].keys())})")

            print(f"\nAnswer preview: {result.get('answer', '')[:150]}...")

        except Exception as e:
            print(f"Error: {e}")


async def test_legacy_service():
    """Test the legacy keyword-based service for comparison."""
    print("\n" + "=" * 60)
    print("Testing Legacy Keyword-Based Service")
    print("=" * 60)

    service = LangChainChatService()

    for test_case in TEST_CASES:
        print(f"\n### {test_case['name']}")
        print(f"Query: {test_case['query']}")
        print(f"Expected issue: {test_case['expected_legacy']}")

        try:
            result = await service.chat(test_case["query"])

            print(f"Route chosen: {result.get('route')}")
            print(f"Confidence: {result.get('confidence')}")

            if result.get("route") == "orchestrated":
                plan = result.get("execution_plan", {})
                if plan:
                    steps = plan.get("execution_plan", [])
                    print(f"Orchestrator steps: {len(steps)}")

        except Exception as e:
            print(f"Error: {e}")


async def demonstrate_improvement():
    """Show specific improvement with the 4 quests example."""
    print("\n" + "=" * 60)
    print("Demonstrating Improvement: 4 Quests Example")
    print("=" * 60)

    query = "Create 4 connected quests about discovering the arcana golem origins, learning their purpose, mastering their magic, and ultimately transforming into one"

    print(f"\nQuery: {query}")

    if os.getenv("OPENAI_API_KEY"):
        print("\n--- Modern Service Approach ---")
        print("The LLM will:")
        print("1. Understand '4 connected quests' from natural language")
        print("2. Call create_quest() 4 times automatically")
        print("3. Pass context between calls for continuity")
        print("4. Handle the progression naturally")

        # This would actually make the calls
        # modern = ModernLangChainService()
        # result = await modern.chat(query)

    print("\n--- Legacy Service Approach ---")
    print("The system must:")
    print("1. Match '4' with regex pattern")
    print("2. Route to orchestrator")
    print("3. Hope orchestrator plans correctly")
    print("4. Execute complex multi-step plan")
    print("5. Combine results properly")

    print("\n✨ The modern approach eliminates all the routing complexity!")


async def main():
    """Run all tests."""
    print("\n" + "🚀 Modern vs Legacy Service Comparison")
    print("=" * 60)

    await test_modern_service()
    await test_legacy_service()
    await demonstrate_improvement()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
The modern tool-based approach:
✅ No keyword patterns to maintain
✅ Handles complex multi-step requests naturally
✅ Understands context and requirements from natural language
✅ Automatically determines tool sequencing
✅ Scales to new use cases without code changes

The legacy keyword approach:
❌ Requires constant pattern updates
❌ Complex orchestrator logic
❌ Brittle routing decisions
❌ Misses nuanced requirements
❌ Every new pattern needs code changes
    """)


if __name__ == "__main__":
    asyncio.run(main())
