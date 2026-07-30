"""Test multi-quest orchestration for epic questlines.

Tests that the orchestrator can properly handle requests for multiple connected quests.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.langchain.chains.agent_orchestrator import AgentOrchestrator


async def test_multi_quest_planning():
    """Test that orchestrator creates multiple quest steps for '4 quests' request."""
    print("Testing multi-quest orchestration planning...")

    orchestrator = AgentOrchestrator()

    # Test request for 4 connected quests
    request = "Create 4 quests that span the player's discovery of the origins and future of the arcana golem race, connected both in theme and execution to build an epic questline"

    # Create execution plan
    plan = await orchestrator._create_execution_plan(request)

    print(f"\nUser intent: {plan.user_intent}")
    print(f"Needs orchestration: {plan.needs_orchestration}")
    print(f"Number of steps: {len(plan.execution_plan)}")

    # Check that it creates multiple quest steps
    quest_steps = [step for step in plan.execution_plan if step.tool == "plan_quest"]
    print(f"Number of quest planning steps: {len(quest_steps)}")

    for i, step in enumerate(plan.execution_plan, 1):
        print(f"\nStep {i}: {step.tool}")
        print(f"  Description: {step.description}")
        if "previous" in str(step.input).lower() or "step_" in str(step.input):
            print("  Uses previous context: Yes")

    # Should have at least 4 quest planning steps
    assert len(quest_steps) >= 4, f"Expected at least 4 quest steps, got {len(quest_steps)}"

    # Should reference previous steps for continuity
    has_references = any("step_" in str(step.input) for step in quest_steps[1:])
    assert has_references, "Later quests should reference previous ones for continuity"

    print("\n✓ Multi-quest orchestration planning successful!")


async def test_questline_description():
    """Test that questline requests are properly understood."""
    print("\n\nTesting questline understanding...")

    orchestrator = AgentOrchestrator()

    # Different ways to request multiple quests
    test_requests = [
        "Create 3 connected quests about discovering ancient ruins",
        "Design a questline with 4 parts exploring the fall of an empire",
        "Make an epic 5-quest saga about becoming a legendary hero",
    ]

    for request in test_requests:
        print(f"\nRequest: {request}")
        plan = await orchestrator._create_execution_plan(request)

        quest_steps = [step for step in plan.execution_plan if step.tool == "plan_quest"]
        print(f"  Generated {len(quest_steps)} quest steps")

        # Extract the number from the request
        import re

        number_match = re.search(r"(\d+)", request)
        expected_quests = int(number_match.group(1)) if number_match else 1

        if len(quest_steps) != expected_quests:
            print(f"  ⚠️  Expected {expected_quests} quests, got {len(quest_steps)}")
        else:
            print("  ✓ Correct number of quests")


async def main():
    """Run all multi-quest tests."""
    print("=" * 60)
    print("Multi-Quest Orchestration Tests")
    print("=" * 60)

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set.")
        print("Tests will use fallback heuristic planning.\n")

    try:
        await test_multi_quest_planning()
        await test_questline_description()

        print("\n" + "=" * 60)
        print("✅ Multi-quest orchestration tests complete!")
        print("The system should now handle requests for multiple")
        print("connected quests and epic questlines properly.")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        print("The orchestrator may need further improvement")
        print("to handle multi-part creative requests.")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
