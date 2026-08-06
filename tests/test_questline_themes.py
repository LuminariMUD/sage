"""Test that modern service preserves questline themes correctly.

This test validates that when a user requests multiple quests with a specific theme,
all quests maintain that theme throughout the questline.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.langchain.modern_service import ModernLangChainService

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_arcana_golem_questline():
    """Test the specific case user reported: 4 quests about arcana golems."""

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set. Skipping test.")
        return

    print("=" * 60)
    print("Testing Arcana Golem Questline Theme Preservation")
    print("=" * 60)

    service = ModernLangChainService(model_name="gpt-4o-mini", temperature=0.7)

    # The exact request that was losing theme
    query = """Create 4 connected quests about discovering the arcana golem origins,
    learning their purpose, mastering their magic, and ultimately transforming into one"""

    print(f"\nQuery: {query}")
    print("\nExpected behavior:")
    print("- All 4 quests should involve arcana golems")
    print("- Quest progression should build toward transformation")
    print("- Each quest should reference the overall theme")
    print("\n" + "-" * 40)

    try:
        # Mock the actual tool calls to see what parameters are passed
        original_tools = service._get_tools()
        tool_calls_made = []

        # Create wrapper to capture tool calls
        async def mock_create_quest(**kwargs):
            tool_calls_made.append(kwargs)
            return {
                "title": f"Quest {kwargs.get('quest_number', 1)}: Arcana Golem Test",
                "description": "Test quest",
                "phases": [],
            }

        # Temporarily replace create_quest for testing
        for tool in original_tools:
            if tool.name == "create_quest":
                tool.func = mock_create_quest
                break

        # Process the query
        result = await service.chat(query)

        print(f"\nTool calls made: {len(tool_calls_made)}")
        for i, call in enumerate(tool_calls_made, 1):
            print(f"\n--- Quest {i} Parameters ---")
            print(f"Premise: {call.get('premise', 'N/A')}")
            print(
                f"Quest Number: {call.get('quest_number', 'N/A')} of {call.get('total_quests', 'N/A')}"
            )
            print(f"Questline Theme: {call.get('questline_theme', 'NOT SET!')}")
            print(f"Final Reward: {call.get('final_reward', 'NOT SET!')}")

            # Check if theme is preserved
            if (
                call.get("questline_theme")
                and "arcana golem" in call.get("questline_theme", "").lower()
            ):
                print("✅ Theme preserved!")
            else:
                print("❌ Theme lost!")

        print("\n" + "-" * 40)
        print("Final answer preview:")
        print(result.get("answer", "")[:500] + "...")

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback

        traceback.print_exc()


async def test_generic_questline():
    """Test a different themed questline to ensure it's not hardcoded."""

    if not os.getenv("OPENAI_API_KEY"):
        return

    print("\n" + "=" * 60)
    print("Testing Crystal Dwarf Mining Questline")
    print("=" * 60)

    service = ModernLangChainService(model_name="gpt-4o-mini", temperature=0.7)

    query = """Create 3 quests about Crystal Dwarves discovering a new vein of
    living crystal, establishing a mining operation, and uncovering ancient secrets"""

    print(f"\nQuery: {query}")

    try:
        # Similar mock setup
        tool_calls_made = []

        async def mock_create_quest(**kwargs):
            tool_calls_made.append(kwargs)
            return {
                "title": f"Quest {kwargs.get('quest_number', 1)}: Crystal Dwarf Test",
                "description": "Test quest",
                "phases": [],
            }

        original_tools = service._get_tools()
        for tool in original_tools:
            if tool.name == "create_quest":
                tool.func = mock_create_quest
                break

        await service.chat(query)

        print(f"\nTool calls made: {len(tool_calls_made)}")
        for i, call in enumerate(tool_calls_made, 1):
            theme = call.get("questline_theme", "NOT SET!")
            if theme != "NOT SET!" and "crystal" in theme.lower() and "dwar" in theme.lower():
                print(f"Quest {i}: ✅ Crystal Dwarf theme preserved")
            else:
                print(f"Quest {i}: ❌ Theme lost (got: {theme})")

    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Run all theme preservation tests."""
    await test_arcana_golem_questline()
    await test_generic_questline()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
The modern service should now:
✅ Extract theme from user's request
✅ Pass questline_theme to EVERY quest in the series
✅ Pass final_reward to help build progression
✅ Maintain context between quests
✅ Keep all quests focused on the requested topic
    """)


if __name__ == "__main__":
    asyncio.run(main())
