#!/usr/bin/env python3
"""Test script for the QuestlineReActAgent."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up environment
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
os.environ["SAGE_API_KEY"] = os.getenv("SAGE_API_KEY", "")
os.environ["SAGE_API_BASE_URL"] = os.getenv("SAGE_API_BASE_URL", "http://localhost:8003")


async def test_direct_agent():
    """Test the QuestlineReActAgent directly."""
    from src.agents.langchain.chains.questline_react import QuestlineReActAgent

    print("=" * 80)
    print("Testing QuestlineReActAgent Directly")
    print("=" * 80)

    agent = QuestlineReActAgent(model_name="gpt-4o", temperature=0.7)

    # Test case 1: 4 quests about Crystal Dwarves
    print("\nTest 1: Generating 4 quests about Crystal Dwarves awakening")
    print("-" * 40)

    try:
        result = await agent.generate_questline(
            premise="Create a questline about Crystal Dwarves awakening from their silicon sleep and rediscovering their ancient memories",
            num_quests=4,
            context_blocks=None,
        )

        print(f"✓ Generated {len(result.get('quests', []))} quests")
        print(f"✓ Reasoning steps: {result['metadata']['reasoning_steps']}")
        print(f"✓ Tools used: {', '.join(result['metadata']['tools_used'])}")

        # Check quest quality
        for quest in result.get("quests", []):
            print(f"\nQuest {quest.get('quest_number', 0)}: {quest.get('title', 'Untitled')}")

            # Check phase descriptions
            for phase in quest.get("phases", []):
                desc_length = len(phase.get("description", "").split())
                status = "✓" if desc_length >= 75 else "✗"
                print(f"  {status} {phase.get('phase', '')}: {desc_length} words")

            # Check for recurring elements
            npcs = quest.get("recurring_npcs", [])
            locs = quest.get("recurring_locations", [])
            if npcs:
                print(f"  Recurring NPCs: {', '.join(npcs)}")
            if locs:
                print(f"  Recurring Locations: {', '.join(locs)}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()


async def test_via_service():
    """Test questline generation through the LangChainChatService."""
    from src.agents.langchain.service import LangChainChatService

    print("\n" + "=" * 80)
    print("Testing via LangChainChatService")
    print("=" * 80)

    service = LangChainChatService(enable_reflection=True)

    # Test cases
    test_cases = [
        "Create 4 quests about Crystal Dwarves awakening",
        "Generate a questline with 3 connected quests following a single hero",
        "Build a 5-quest series that spans three different regions of Luminari",
    ]

    for i, test_message in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_message}")
        print("-" * 40)

        try:
            result = await service.chat(test_message)

            route = result.get("route", "unknown")
            print(f"✓ Route: {route}")

            if route == "questline_generation":
                questline = result.get("questline", {})
                quests = questline.get("quests", [])
                print(f"✓ Generated {len(quests)} quests")

                # Show quest titles
                for quest in quests:
                    print(
                        f"  - Quest {quest.get('quest_number', 0)}: {quest.get('title', 'Untitled')}"
                    )
            else:
                print(f"✗ Unexpected route: {route}")
                print(f"  Answer preview: {result.get('answer', '')[:200]}...")

        except Exception as e:
            print(f"✗ Error: {e}")


async def test_streaming():
    """Test streaming questline generation."""
    from src.agents.langchain.chains.questline_react import QuestlineReActAgent

    print("\n" + "=" * 80)
    print("Testing Streaming Generation")
    print("=" * 80)

    agent = QuestlineReActAgent()

    print("\nGenerating questline with streaming updates...")
    print("-" * 40)

    try:
        async for event in agent.stream_questline_generation(
            premise="Create an epic questline about discovering the truth behind the Prisoner's locks",
            num_quests=3,
            context_blocks=None,
        ):
            event_type = event.get("type", "")
            content = event.get("content", "")

            if event_type == "status":
                print(f"[STATUS] {content}")
            elif event_type == "quest_generated":
                quest = event.get("data", {})
                print(f"[QUEST] {content}")
                # Validate quest quality
                phases = quest.get("phases", [])
                if phases:
                    avg_words = sum(len(p.get("description", "").split()) for p in phases) / len(
                        phases
                    )
                    print(f"        Average phase length: {avg_words:.1f} words")
            elif event_type == "complete":
                print(f"[COMPLETE] {content}")
                questline = event.get("data", {})
                print(f"Final questline has {len(questline.get('quests', []))} quests")

    except Exception as e:
        print(f"✗ Streaming error: {e}")
        import traceback

        traceback.print_exc()


async def main():
    """Run all tests."""
    print("QuestlineReActAgent Test Suite")
    print("=" * 80)
    print("Configuration:")
    print(f"  OpenAI API Key: {'Set' if os.getenv('OPENAI_API_KEY') else 'Missing'}")
    print(f"  Sage API Key: {'Set' if os.getenv('SAGE_API_KEY') else 'Missing'}")
    print(f"  API Base URL: {os.getenv('SAGE_API_BASE_URL', 'http://localhost:8003')}")
    print()

    # Run tests
    await test_direct_agent()
    await test_via_service()
    await test_streaming()

    print("\n" + "=" * 80)
    print("Test Suite Complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
