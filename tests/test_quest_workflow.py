#!/usr/bin/env python3
"""Test script to debug quest workflow stopping after phase 1."""

import asyncio
import json
import logging
import sys

# Add src to path
sys.path.insert(0, "/app/src")

from agents.langchain.quest_workflow import QuestWorkflow

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_workflow():
    """Test the quest workflow to see where it stops."""

    workflow = QuestWorkflow()

    requirements = """Create a quest where the player helps a village herbalist gather rare mushrooms,
    but then discovers the herbalist is actually a wizard who needs the mushrooms for a ritual
    to seal an ancient evil in nearby ruins."""

    print("Starting quest workflow test...")
    print(f"Requirements: {requirements}\n")

    # Track workflow execution
    initial_state = {
        "requirements": requirements,
        "lore_context": [],
        "quest_hook": {},
        "phase_1": {},
        "phase_2": {},
        "phase_3": {},
        "phase_4": None,
        "phase_5": None,
        "resolution": "",
        "rewards": {},
        "quest_title": "",
        "phase_count": 0,
        "current_phase": 0,
        "complete_quest": {},
    }

    print("Running workflow with streaming to see each step...")

    # Use streaming to see what's happening
    step_count = 0
    async for event in workflow.app.astream(initial_state):
        step_count += 1
        print(f"\n=== Step {step_count} ===")
        for node_name, node_state in event.items():
            print(f"Node: {node_name}")

            # Show what was added/changed
            if node_name == "create_hook" and node_state.get("quest_hook"):
                print(
                    f"  - Created hook: {node_state['quest_hook'].get('quest_title', 'No title')}"
                )
            elif node_name == "create_phase_1" and node_state.get("phase_1"):
                print(f"  - Created phase 1: {node_state['phase_1'].get('phase_name', 'No name')}")
                print(f"  - Current phase: {node_state.get('current_phase', 0)}")
            elif node_name == "create_phase_2" and node_state.get("phase_2"):
                print(f"  - Created phase 2: {node_state['phase_2'].get('phase_name', 'No name')}")
                print(f"  - Current phase: {node_state.get('current_phase', 0)}")
            elif node_name == "create_phase_3" and node_state.get("phase_3"):
                print(f"  - Created phase 3: {node_state['phase_3'].get('phase_name', 'No name')}")
                print(f"  - Current phase: {node_state.get('current_phase', 0)}")
                print(f"  - Phase count: {node_state.get('phase_count', 0)}")
            elif node_name == "check_additional_phases":
                print("  - Checking if more phases needed...")
                print(f"  - Current phase: {node_state.get('current_phase', 0)}")
            elif node_name == "create_phase_4" and node_state.get("phase_4"):
                print(f"  - Created phase 4: {node_state['phase_4'].get('phase_name', 'No name')}")
            elif node_name == "create_resolution" and node_state.get("resolution"):
                print("  - Created resolution")
            elif node_name == "create_rewards" and node_state.get("rewards"):
                print("  - Created rewards")
            elif node_name == "compile_quest" and node_state.get("complete_quest"):
                print("  - Compiled complete quest")
                print(f"  - Total phases: {node_state['complete_quest'].get('total_phases', 0)}")

    print(f"\n\nWorkflow completed after {step_count} steps")

    # Also run normally to get final result
    print("\n\n=== Running workflow normally ===")
    result = await workflow.build_quest(requirements)

    print("\n=== Final Quest Result ===")
    print(json.dumps(result, indent=2))

    # Check what phases were created
    if result.get("phases"):
        print(f"\nTotal phases created: {len(result['phases'])}")
        for i, phase in enumerate(result["phases"], 1):
            print(f"  Phase {i}: {phase.get('phase_name', 'Unnamed')}")
    else:
        print("\nNo phases found in result!")


if __name__ == "__main__":
    asyncio.run(test_workflow())
