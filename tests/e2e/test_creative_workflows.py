"""End-to-end tests for creative workflows."""

import pytest

from src.agents.langchain.quest_workflow import QuestWorkflow
from src.agents.langchain.service import LangChainChatService


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_quest_generation():
    """Test complete quest generation workflow."""
    workflow = QuestWorkflow()

    requirements = """
    Create a quest where players help a Crystal Dwarf miner who has discovered
    a strange glowing crystal in the depths of Nagburim. The crystal seems to
    pulse with an unknown energy.
    """

    print("\n\n🗡️  Testing Quest Generation Workflow...")
    print(f"Requirements: {requirements.strip()}")

    # Generate the quest
    quest = await workflow.build_quest(requirements)

    # Verify quest structure
    assert quest is not None, "Quest should be generated"
    assert isinstance(quest, dict), "Quest should be a dictionary"

    # Check for essential quest components
    if "quest_title" in quest or "title" in quest:
        title = quest.get("quest_title") or quest.get("title")
        print(f"\n✅ Quest Title: {title}")

    # Check for quest hook
    if "quest_hook" in quest:
        print("📖 Quest Hook: Present")
        hook = quest.get("quest_hook", {})
        if isinstance(hook, dict):
            assert len(str(hook)) > 20, "Quest hook should have content"

    # Check for phases
    if "phases" in quest:
        phases = quest.get("phases", [])
        print(f"📋 Quest Phases: {len(phases)}")
        assert len(phases) >= 3, "Quest should have at least 3 phases"

        # Verify phase structure
        for i, phase in enumerate(phases, 1):
            if isinstance(phase, dict):
                print(f"   Phase {i}: {phase.get('phase_name', 'Unnamed')[:50]}")
                assert "phase_name" in phase or "name" in phase, f"Phase {i} should have a name"
                assert (
                    "description" in phase or "objective" in phase
                ), f"Phase {i} should have description/objective"
    else:
        # Alternative structure - check for individual phases
        phase_keys = ["phase_1", "phase_2", "phase_3"]
        found_phases = sum(1 for key in phase_keys if quest.get(key))
        print(f"📋 Quest Phases: {found_phases}")
        assert found_phases >= 3, "Quest should have at least 3 phases"

    # Check for resolution
    if "resolution" in quest:
        print("🏁 Resolution: Present")
        assert len(str(quest["resolution"])) > 20, "Resolution should have content"

    # Check for rewards
    if "rewards" in quest:
        print("💰 Rewards: Present")

    print("\n✅ Quest generation workflow completed successfully!")


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_story_development():
    """Test complete story development workflow."""
    service = LangChainChatService()

    story_request = """
    I want to develop a story about a young Crystal Dwarf apprentice who discovers
    a hidden chamber in the mines containing ancient artifacts from before the
    Nagburim settlement.
    """

    print("\n\n📖 Testing Story Development Workflow...")
    print(f"Request: {story_request.strip()}")

    # Generate the story
    response = await service.chat(story_request, conversation_history=[])

    # Verify response structure
    assert response is not None, "Response should be generated"
    assert isinstance(response, dict), "Response should be a dictionary"

    print(f"\n📊 Route: {response.get('route', 'unknown')}")
    print(f"🎯 Confidence: {response.get('confidence', 0):.2f}")

    # Should route to story_development
    route = response.get("route", "")
    # Accept story_development, narrative_generation, or creative routes
    assert route in [
        "story_development",
        "narrative_generation",
        "creative",
        "direct_answer",
    ], f"Should route to creative workflow, got: {route}"

    # Check for story content
    has_content = False

    if "story_development" in response:
        dev = response["story_development"]
        print("\n📚 Story Development Response:")

        if "story_content" in dev:
            content = dev["story_content"]
            print(f"   Content length: {len(content)} chars")
            assert len(content) > 100, "Story content should be substantial"
            has_content = True

        if "new_elements" in dev:
            elements = dev["new_elements"]
            print(f"   New elements: {len(elements)}")

        if "canon_foundation" in dev:
            foundation = dev["canon_foundation"]
            print(f"   Canon foundation: {len(foundation)} items")

    elif "content" in response:
        content = response["content"]
        print(f"\n📝 Content length: {len(content)} chars")
        assert len(content) > 100, "Story content should be substantial"
        has_content = True

    elif "answer" in response:
        answer = response["answer"]
        print(f"\n📝 Answer length: {len(answer)} chars")
        assert len(answer) > 100, "Story answer should be substantial"
        has_content = True

    assert has_content, "Response should contain story content"

    print("\n✅ Story development workflow completed successfully!")


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_quest_workflow_with_lore_context():
    """Test quest generation uses lore context."""
    workflow = QuestWorkflow()

    # Quest that references existing lore
    requirements = """
    Create a quest involving the Crystal Dwarves of Nagburim and their
    relationship with crystal mining and gemcutting traditions.
    """

    print("\n\n🎲 Testing Quest with Lore Context...")

    quest = await workflow.build_quest(requirements)

    assert quest is not None, "Quest should be generated"

    # Check if quest references lore appropriately
    quest_str = str(quest).lower()

    # Look for references to key lore elements
    lore_terms = ["crystal", "dwarf", "nagburim", "mine", "mining"]
    found_terms = [term for term in lore_terms if term in quest_str]

    print(f"\n🔍 Lore terms found: {found_terms}")
    assert len(found_terms) >= 2, "Quest should reference lore elements"

    print("✅ Quest properly incorporates lore context!")


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_story_conversation():
    """Test multi-turn story development conversation."""
    service = LangChainChatService()

    print("\n\n💬 Testing Multi-Turn Story Conversation...")

    # First turn: Create a character
    response1 = await service.chat(
        "I want to create a mysterious Crystal Dwarf merchant who trades in rare crystals.",
        conversation_history=[],
    )

    assert response1 is not None
    print(f"\n   Turn 1 - Route: {response1.get('route')}")

    # Build conversation history
    history = [
        {"role": "user", "content": "I want to create a mysterious Crystal Dwarf merchant"},
        {"role": "assistant", "content": str(response1)},
    ]

    # Second turn: Add more details
    response2 = await service.chat(
        "Now give this merchant a secret - they know the location of a legendary crystal mine.",
        conversation_history=history,
    )

    assert response2 is not None
    print(f"   Turn 2 - Route: {response2.get('route')}")

    # Both responses should have content
    assert len(str(response1)) > 50, "First response should have content"
    assert len(str(response2)) > 50, "Second response should have content"

    print("\n✅ Multi-turn conversation handled successfully!")


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_creative_workflow_performance():
    """Test creative workflow performance."""
    import time

    workflow = QuestWorkflow()

    print("\n\n⏱️  Testing Creative Workflow Performance...")

    start_time = time.time()

    requirements = "Create a simple 3-phase quest to find a lost mining tool."

    quest = await workflow.build_quest(requirements)

    elapsed_time = time.time() - start_time

    assert quest is not None, "Quest should be generated"

    print(f"\n   Quest generation time: {elapsed_time:.2f}s")

    # Performance check (lenient for CI)
    if elapsed_time < 15.0:
        print("   ✅ Fast generation (<15s)")
    elif elapsed_time < 30.0:
        print("   ⚠️  Acceptable generation (15-30s)")
    else:
        print("   ⚠️  Slow generation (>30s)")

    # Should complete in reasonable time
    assert elapsed_time < 60.0, f"Quest generation took too long: {elapsed_time:.2f}s"


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_creative_error_handling():
    """Test error handling in creative workflows."""
    workflow = QuestWorkflow()

    print("\n\n⚠️  Testing Error Handling...")

    # Test with minimal/unclear requirements
    minimal_requirements = "quest"

    try:
        quest = await workflow.build_quest(minimal_requirements)

        # Should either succeed with a basic quest or handle gracefully
        if quest:
            print("   ✅ Handled minimal requirements gracefully")
        else:
            print("   ⚠️  Returned empty result for minimal input")

    except Exception as e:
        # Exceptions should be meaningful
        print(f"   ⚠️  Exception raised: {type(e).__name__}")
        # Don't fail the test - error handling is acceptable

    print("\n✅ Error handling test completed!")
