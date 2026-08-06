#!/usr/bin/env python3
"""Test script for story development functionality"""

import asyncio
import json

import pytest

from src.agents.langchain.service import LangChainChatService

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_story_development():
    """Test the story development chain"""
    service = LangChainChatService()

    # Test 1: Create a new character
    print("\n=== Test 1: Create a new character ===")
    response = await service.chat(
        "I want to develop a new story about a rogue Crystal Dwarf who left the Crystalline Network. Can you help me create this character?",
        conversation_history=[],
    )
    print(f"Route: {response.get('route')}")
    print(f"Confidence: {response.get('confidence')}")

    if response.get("route") == "story_development":
        dev = response.get("story_development", {})
        print(f"\nCanon Foundation: {dev.get('canon_foundation', [])}")
        print(f"\nNew Elements: {json.dumps(dev.get('new_elements', []), indent=2)}")
        print(f"\nStory Content:\n{dev.get('story_content', '')[:500]}...")
        print(f"\nContinuity Notes: {dev.get('continuity_notes', '')}")
    else:
        print(f"Unexpected route: {response}")

    # Test 2: Expand the story
    print("\n\n=== Test 2: Expand the story ===")
    response2 = await service.chat(
        "Now I want to create a location where this character hides - perhaps an abandoned mine that interferes with the Network's connection. What would this place be like?",
        conversation_history=[
            {
                "role": "user",
                "content": "I want to develop a new story about a rogue Crystal Dwarf",
            },
            {"role": "assistant", "content": "Created character..."},
        ],
    )
    print(f"Route: {response2.get('route')}")

    if response2.get("route") == "story_development":
        dev2 = response2.get("story_development", {})
        print(f"\nNew Elements: {json.dumps(dev2.get('new_elements', []), indent=2)}")
        print(f"\nTotal Story Elements: {dev2.get('total_story_elements', 0)}")

    # Test 3: Test classifier patterns
    print("\n\n=== Test 3: Test classifier patterns ===")
    test_messages = [
        "Tell me about the Crystal Dwarves",  # Should be lore_query
        "Create a new villain for my campaign",  # Should be story_development
        "Write a scene where Thrain meets Elara",  # Should be narrative_generation
        "Plan a quest to retrieve the Eye of Thanastis",  # Should be quest_planning
        "What can you help me with?",  # Should be meta_help
        "I want to imagine what if the Prisoner escaped",  # Should be story_development
    ]

    for msg in test_messages:
        response = await service.chat(msg)
        print(
            f"'{msg[:50]}...' -> {response.get('route')} (confidence: {response.get('confidence')})"
        )


if __name__ == "__main__":
    asyncio.run(test_story_development())
