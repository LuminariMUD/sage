"""
Quest Building Workflow for LuminariMUD
A sequential workflow that builds quests with proper context preservation.
"""

import json
import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from src.llm.langchain_helpers import get_chat_model


def _extract_json_content(content: str | list[Any] | dict[str, Any]) -> str:
    """Pull JSON payload text out of common markdown wrappers."""

    if content is None:
        return ""

    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(json.dumps(item))
            else:
                parts.append(str(item))
        text = "\n".join(parts).strip()
    elif isinstance(content, dict):
        return json.dumps(content)
    else:
        text = str(content).strip()

    if not text:
        return ""

    for fence in ("```json", "```JSON"):
        if fence in text:
            try:
                after = text.split(fence, 1)[1]
            except IndexError:
                continue
            segment = after.split("```", 1)[0].strip()
            if segment:
                return segment
    if "```" in text:
        segment = text.split("```", 1)[1].split("```", 1)[0].strip()
        if segment:
            return segment

    return text


logger = logging.getLogger(__name__)


class QuestState(TypedDict):
    """State for quest building workflow."""

    # Input
    requirements: str  # Original user requirements
    lore_context: list[dict[str, Any]]  # Relevant lore from search

    # Progressive building
    quest_hook: dict[str, Any]
    phase_1: dict[str, Any]
    phase_2: dict[str, Any]
    phase_3: dict[str, Any]
    phase_4: dict[str, Any] | None  # Optional 4th phase
    phase_5: dict[str, Any] | None  # Optional 5th phase
    resolution: str
    rewards: dict[str, Any]

    # Metadata
    quest_title: str
    phase_count: int
    current_phase: int

    # Final output
    complete_quest: dict[str, Any]


class QuestWorkflow:
    """Sequential workflow for building complete quests."""

    def __init__(self):
        # Use creative task for quest generation with provider abstraction
        self.llm = get_chat_model(task="creative", temperature=0.8, streaming=False)
        self.graph = self._build_graph()
        self.app = self.graph.compile()

    def _build_graph(self) -> StateGraph:
        """Build the quest workflow graph."""
        graph = StateGraph(QuestState)

        # Add nodes in sequence
        graph.add_node("create_hook", self._create_hook)
        graph.add_node("create_phase_1", self._create_phase_1)
        graph.add_node("create_phase_2", self._create_phase_2)
        graph.add_node("create_phase_3", self._create_phase_3)
        graph.add_node("check_additional_phases", self._check_additional_phases)
        graph.add_node("create_phase_4", self._create_phase_4)
        graph.add_node("create_phase_5", self._create_phase_5)
        graph.add_node("create_resolution", self._create_resolution)
        graph.add_node("create_rewards", self._create_rewards)
        graph.add_node("compile_quest", self._compile_quest)

        # Set entry point
        graph.set_entry_point("create_hook")

        # Add sequential edges
        graph.add_edge("create_hook", "create_phase_1")
        graph.add_edge("create_phase_1", "create_phase_2")
        graph.add_edge("create_phase_2", "create_phase_3")
        graph.add_edge("create_phase_3", "check_additional_phases")

        # Conditional routing for additional phases
        graph.add_conditional_edges(
            "check_additional_phases",
            self._should_add_more_phases,
            {
                "phase_4": "create_phase_4",
                "phase_5": "create_phase_5",
                "resolution": "create_resolution",
            },
        )

        graph.add_conditional_edges(
            "create_phase_4",
            lambda s: self._should_add_more_phases(s),
            {"phase_5": "create_phase_5", "resolution": "create_resolution"},
        )

        graph.add_edge("create_phase_5", "create_resolution")
        graph.add_edge("create_resolution", "create_rewards")
        graph.add_edge("create_rewards", "compile_quest")
        graph.add_edge("compile_quest", END)

        return graph

    def _format_lore_context(self, lore_context: list) -> str:
        """Format lore context for inclusion in prompts."""
        if not lore_context:
            return "No specific lore context available"

        lore_summary = ""
        for i, lore_item in enumerate(lore_context[:10], 1):  # Use up to 10 items
            if isinstance(lore_item, dict):
                text = lore_item.get("text", lore_item.get("content", str(lore_item)))
            else:
                text = str(lore_item)
            lore_summary += f"\n{i}. {text}\n"
        return lore_summary

    def _extract_narrative_requirements(self, requirements: str) -> dict[str, Any]:
        """Extract key narrative elements from user requirements."""
        prompt = f"""Analyze these quest requirements and extract the key narrative elements:

Requirements: {requirements}

Extract:
1. Main protagonist type (e.g., "the player", "adventurer")
2. Initial helper NPC description
3. Initial objective/resource gathering
4. Mid-quest twist or escalation
5. Hidden antagonist reveal
6. Final confrontation type
7. Resolution and reward hints
8. Any specific names, locations, or items mentioned

Return as JSON with these keys: protagonist, helper_npc, initial_objective,
mid_twist, antagonist_reveal, final_confrontation, resolution_hints, specific_details"""

        response = self.llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)
        try:
            return json.loads(raw)
        except Exception as exc:
            logger.warning(
                "Failed to parse narrative requirements JSON (%s)",
                type(exc).__name__,
            )
            # Fallback to basic extraction
            return {"protagonist": "the player", "requirements": requirements}

    async def _create_hook(self, state: QuestState) -> dict[str, Any]:
        """Create the quest hook based on requirements and lore."""
        requirements = state["requirements"]
        lore_context = state.get("lore_context", [])

        # Extract narrative structure
        narrative = self._extract_narrative_requirements(requirements)

        # Format full lore context properly
        lore_summary = self._format_lore_context(lore_context)

        prompt = f"""Create a quest hook for LuminariMUD based on these requirements:

USER REQUIREMENTS: {requirements}

NARRATIVE STRUCTURE EXTRACTED:
{json.dumps(narrative, indent=2)}

RELEVANT LORE CONTEXT:
{lore_summary}

CRITICAL REQUIREMENTS:
- The PLAYER must be the protagonist and primary actor
- Frame all objectives as actions the PLAYER will take
- NPCs provide information or support but NEVER solve problems for the player
- Use "you" to address the player directly

Create a compelling quest hook that:
1. Introduces the initial helper NPC as described in requirements
2. Sets up objectives that the PLAYER must accomplish
3. Hints at larger mysteries without revealing them
4. Uses specific names/locations from lore context accurately
5. Establishes the PLAYER as the hero who drives the story

Return JSON with:
- hook: The narrative hook text (2-3 paragraphs)
- initial_npc: Name and description of the helper
- initial_objective: Clear statement of what to gather
- locations: List of 2-3 key locations
- quest_title: Epic title for the quest"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            hook_data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse quest hook JSON (%s)", type(exc).__name__)
            # Parse as text if not JSON
            hook_data = {
                "hook": response.content,
                "initial_npc": narrative.get("helper_npc", "village herbalist"),
                "initial_objective": narrative.get("initial_objective", "gather resources"),
                "locations": ["village", "forest", "ruins"],
                "quest_title": "The Hidden Agenda",
            }

        state["quest_hook"] = hook_data
        state["quest_title"] = hook_data.get("quest_title", "Epic Quest")
        return state

    async def _create_phase_1(self, state: QuestState) -> dict[str, Any]:
        """Create Phase 1 based on narrative requirements."""
        requirements = state["requirements"]
        hook = state["quest_hook"]
        lore_context = state.get("lore_context", [])
        narrative = self._extract_narrative_requirements(requirements)

        # Format lore context
        lore_summary = self._format_lore_context(lore_context)

        prompt = f"""Create Phase 1 of the quest based on these requirements:

USER REQUIREMENTS: {requirements}

QUEST HOOK ESTABLISHED:
{json.dumps(hook, indent=2)}

NARRATIVE EXTRACTED: {json.dumps(narrative, indent=2)}

LORE CONTEXT (use this for accurate character/location details):
{lore_summary}

CRITICAL: The PLAYER is the protagonist!
- All main actions must be performed BY the player
- NPCs guide but never do the important work
- Frame objectives as "You must..." not "The NPC will..."

Create the FIRST PHASE that:
- Directly follows from the hook
- Advances the story with PLAYER as the active agent
- Uses characters/locations from lore context accurately
- Can include any type of activity (gathering, investigation, combat, social, exploration)
- Sets up future phases naturally

Return JSON with:
- phase_name: (descriptive name for this phase)
- description: Detailed phase narrative (2-3 paragraphs)
- objectives: List of specific tasks
- npcs: [{{"name": "...", "role": "..."}}]
- challenges: List of obstacles/conflicts
- completion_trigger: What completes this phase"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            phase_data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse phase 1 JSON (%s)", type(exc).__name__)
            phase_data = {
                "phase_name": "Resource Gathering",
                "description": response.content,
                "objectives": ["Gather resources"],
                "npcs": [{"name": hook.get("initial_npc", "Helper"), "role": "Quest giver"}],
                "completion_trigger": "Return resources to NPC",
            }

        state["phase_1"] = phase_data
        state["current_phase"] = 1
        return state

    async def _create_phase_2(self, state: QuestState) -> dict[str, Any]:
        """Create Phase 2 based on narrative flow."""
        requirements = state["requirements"]
        hook = state["quest_hook"]
        phase1 = state["phase_1"]
        lore_context = state.get("lore_context", [])

        lore_summary = self._format_lore_context(lore_context)

        prompt = f"""Create Phase 2 of the quest:

USER REQUIREMENTS: {requirements}

STORY SO FAR:
Hook: {hook.get("hook", "")[:300]}...
Phase 1: {phase1.get("description", "")[:300]}...

LORE CONTEXT (use for accurate character/location details):
{lore_summary}

CRITICAL: The PLAYER is the protagonist!
- The PLAYER takes action, NPCs react
- Use "You must..." not "The NPC will..."
- Player drives the narrative forward

Create the SECOND PHASE that:
- Naturally continues from Phase 1
- Escalates tension or introduces complications
- Advances with PLAYER as the active agent
- Uses lore context for accurate character portrayals
- Can be any type of content the story needs

Return JSON with:
- phase_name: (descriptive name)
- description: Detailed phase narrative (2-3 paragraphs)
- objectives: List of tasks
- npcs: [{{"name": "...", "role": "..."}}]
- challenges: Obstacles/conflicts
- new_elements: Any new locations/items/revelations
- completion_trigger: What completes this phase"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            phase_data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse phase 2 JSON (%s)", type(exc).__name__)
            phase_data = {
                "phase_name": "The Wizard's Interest",
                "description": response.content,
                "objectives": ["Meet the wizard", "Explore with map"],
                "npcs": [{"name": "Mysterious Wizard", "role": "New quest giver"}],
                "completion_trigger": "Report findings to wizard",
            }

        state["phase_2"] = phase_data
        state["current_phase"] = 2
        return state

    async def _create_phase_3(self, state: QuestState) -> dict[str, Any]:
        """Create Phase 3 based on narrative progression."""
        requirements = state["requirements"]
        phase1 = state["phase_1"]
        phase2 = state["phase_2"]
        lore_context = state.get("lore_context", [])

        lore_summary = self._format_lore_context(lore_context)

        prompt = f"""Create Phase 3 of the quest:

USER REQUIREMENTS: {requirements}

STORY PROGRESSION:
Phase 1: {phase1.get("description", "")[:300]}...
Phase 2: {phase2.get("description", "")[:300]}...

LORE CONTEXT (essential for accuracy):
{lore_summary}

CRITICAL: The PLAYER is the hero of this story!
- The PLAYER confronts the main challenges
- The PLAYER makes key discoveries and decisions
- NPCs provide context but the PLAYER takes action

Create the THIRD PHASE that:
- Continues the narrative naturally
- May serve as climax OR build toward it
- Centers the PLAYER as the active protagonist
- Uses lore accurately (especially named characters)
- Provides meaningful progression

If this seems like it should be the final action phase, make it climactic.
If the story needs more buildup, make it escalate tension.

Return JSON with:
- phase_name: (descriptive name)
- description: Detailed phase narrative (2-3 paragraphs)
- objectives: List of tasks
- npcs: [{{"name": "...", "role": "..."}}]
- challenges: Obstacles/conflicts
- key_elements: Important items/revelations/conflicts
- completion_trigger: What completes this phase
- narrative_note: Is this climactic or building?"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            phase_data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse phase 3 JSON (%s)", type(exc).__name__)
            phase_data = {
                "phase_name": "The Ruins Expedition",
                "description": response.content,
                "objectives": ["Retrieve the mysterious item"],
                "target_item": "Ancient artifact",
                "completion_trigger": "Obtain the item from ruins",
            }

        state["phase_3"] = phase_data
        state["current_phase"] = 3
        state["phase_count"] = 3  # Base 3 phases
        return state

    def _should_add_more_phases(self, state: QuestState) -> str:
        """Decide if we need more phases based on narrative complexity."""
        # Let the story structure decide
        current_phase = state.get("current_phase", 0)
        requirements = state.get("requirements", "")

        if current_phase >= 5:
            # Maximum 5 phases
            return "resolution"
        elif current_phase < 3:
            # Minimum 3 phases - keep going (but this shouldn't happen with our flow)
            return "phase_4"
        elif current_phase == 3:
            # After phase 3, check if we need phase 4
            # Check the narrative requirements for complexity indicators
            req_lower = requirements.lower()
            complexity_indicators = [
                "then" in req_lower
                and req_lower.count("then") > 2,  # Multiple "thens" suggest phases
                "after" in req_lower and req_lower.count("after") > 1,  # Multiple "afters"
                "phases" in req_lower or "phase" in req_lower,  # Explicit phase mentions
                len(requirements) > 500,  # Long detailed requirements
                "finally" in req_lower or "climax" in req_lower or "confrontation" in req_lower,
            ]

            if sum(complexity_indicators) >= 2:
                return "phase_4"
            return "resolution"
        elif current_phase == 4:
            # After phase 4, rarely need phase 5 unless very complex
            if "epic" in requirements.lower() and len(requirements) > 600:
                return "phase_5"
            return "resolution"
        else:
            return "resolution"

    async def _create_phase_4(self, state: QuestState) -> dict[str, Any]:
        """Create Phase 4 if needed by narrative."""
        requirements = state["requirements"]
        phase3 = state["phase_3"]
        lore_context = state.get("lore_context", [])
        all_phases = f"Phase 1: {state['phase_1'].get('description', '')[:200]}\nPhase 2: {state['phase_2'].get('description', '')[:200]}\nPhase 3: {phase3.get('description', '')[:200]}"

        lore_summary = self._format_lore_context(lore_context)

        prompt = f"""Create Phase 4 of the quest:

USER REQUIREMENTS: {requirements}

STORY SO FAR:
{all_phases}

LORE CONTEXT (maintain accuracy):
{lore_summary}

CRITICAL: The PLAYER must be the hero!
- The PLAYER performs the climactic actions
- The PLAYER's choices determine outcomes
- NPCs witness the PLAYER's heroism

Create the FOURTH PHASE that:
- Advances from Phase 3 naturally
- Moves toward resolution of the requirements
- Centers the PLAYER in all action
- Uses lore context accurately for all named entities
- Maintains all continuity

Return JSON with:
- phase_name: (descriptive name)
- description: Detailed phase narrative (2-3 paragraphs)
- objectives: List of tasks
- npcs: [{{"name": "...", "role": "..."}}]
- challenges: Obstacles/conflicts
- key_elements: Important developments
- completion_trigger: What completes this phase
- is_climax: true/false"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            phase_data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse phase 4 JSON (%s)", type(exc).__name__)
            phase_data = {
                "phase_name": "The Wizard's Betrayal",
                "description": response.content,
                "objectives": ["Defeat the mad wizard"],
                "completion_trigger": "Wizard defeated",
            }

        state["phase_4"] = phase_data
        state["current_phase"] = 4
        state["phase_count"] = 4
        return state

    async def _check_additional_phases(self, state: QuestState) -> dict[str, Any]:
        """Just pass through - routing logic is in conditional edges."""
        return state

    async def _create_phase_5(self, state: QuestState) -> dict[str, Any]:
        """Create Phase 5 if needed for complex narratives."""
        requirements = state["requirements"]

        prompt = f"""Create Phase 5 of the quest (FINAL ACTION PHASE):

USER REQUIREMENTS: {requirements}

This is the FINAL action phase before resolution.
Previous phases have built up to this moment.

Create the FIFTH PHASE that:
- Provides the climactic conclusion to the action
- Resolves the main conflict
- Delivers on the promise of the requirements
- Sets up for the resolution/rewards

Return JSON with:
- phase_name: (descriptive name)
- description: Detailed phase narrative (2-3 paragraphs)
- objectives: Final tasks
- npcs: [{{"name": "...", "role": "..."}}]
- final_challenge: The ultimate obstacle
- completion_trigger: What completes the quest action"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            phase_data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse phase 5 JSON (%s)", type(exc).__name__)
            phase_data = {
                "phase_name": "Final Confrontation",
                "description": response.content,
                "completion_trigger": "Complete the final challenge",
            }

        state["phase_5"] = phase_data
        state["current_phase"] = 5
        state["phase_count"] = 5
        return state

    async def _create_resolution(self, state: QuestState) -> dict[str, Any]:
        """Create the quest resolution."""
        # Get the last phase that was created
        final_phase = state.get("phase_5") or state.get("phase_4") or state.get("phase_3")
        final_phase_desc = (
            final_phase.get("description", "") if final_phase else "Quest phases completed"
        )

        prompt = f"""Create the quest resolution:

FINAL PHASE: {final_phase_desc}

Create a satisfying resolution that:
1. Describes the aftermath of the final confrontation/challenge
2. Explains what happens to key items/artifacts
3. Shows how the area/community is affected
4. Hints at future adventures
5. Provides closure while leaving some mystery

Write 2-3 paragraphs of resolution narrative."""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        state["resolution"] = response.content
        return state

    async def _create_rewards(self, state: QuestState) -> dict[str, Any]:
        """Create quest rewards."""
        # Find any key items mentioned in phases
        key_items = []
        for phase_key in ["phase_3", "phase_4", "phase_5"]:
            phase = state.get(phase_key, {})
            if phase and isinstance(phase, dict):
                if phase.get("target_item"):
                    key_items.append(phase["target_item"])
                if phase.get("key_elements"):
                    key_items.extend(phase.get("key_elements", []))

        item_context = key_items[0] if key_items else "quest completion"
        resolution = state.get("resolution", "quest completed successfully")

        prompt = f"""Create quest rewards based on this quest resolution:

{resolution[:500]}

Key items involved: {", ".join(key_items) if key_items else "various quest items"}

Create rewards including:
1. The artifact itself (now usable by player)
2. Experience points (substantial for epic quest)
3. Gold/currency reward
4. Reputation gains
5. Optional: New ability or spell learned

Return JSON with:
- item_reward: {{"name": "...", "description": "...", "properties": "..."}}
- experience: Amount of XP
- gold: Currency amount
- reputation: Faction reputation gains
- special_reward: Any unique rewards"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        raw = _extract_json_content(response.content)

        try:
            rewards = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse rewards JSON (%s)", type(exc).__name__)
            rewards = {
                "item_reward": {
                    "name": item_context,
                    "description": "The artifact, now yours to wield",
                    "properties": "Magical enhancement",
                },
                "experience": 5000,
                "gold": 1000,
                "reputation": "Hero of the village",
            }

        state["rewards"] = rewards
        return state

    async def _compile_quest(self, state: QuestState) -> dict[str, Any]:
        """Compile the complete quest."""

        # Build phase list
        phases = [state["phase_1"], state["phase_2"], state["phase_3"]]
        if state.get("phase_4"):
            phases.append(state["phase_4"])
        if state.get("phase_5"):
            phases.append(state["phase_5"])

        complete_quest = {
            "title": state["quest_title"],
            "hook": state["quest_hook"],
            "phases": phases,
            "resolution": state["resolution"],
            "rewards": state["rewards"],
            "total_phases": len(phases),
            "narrative_type": "epic_quest_with_betrayal",
        }

        state["complete_quest"] = complete_quest
        return state

    async def build_quest(
        self, requirements: str, lore_context: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Build a complete quest with the workflow."""

        initial_state = {
            "requirements": requirements,
            "lore_context": lore_context or [],
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

        # Run the workflow
        result = await self.app.ainvoke(initial_state)

        return result["complete_quest"]

    async def build_quest_streaming(
        self, requirements: str, lore_context: list[dict[str, Any]] | None = None
    ):
        """Build quest with streaming updates."""

        initial_state = {
            "requirements": requirements,
            "lore_context": lore_context or [],
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

        # Stream the workflow execution
        async for event in self.app.astream(initial_state):
            # Yield progress updates
            for node_name, node_state in event.items():
                if node_name == "create_hook":
                    yield {"status": "creating_hook", "data": node_state.get("quest_hook")}
                elif node_name == "create_phase_1":
                    yield {"status": "creating_phase_1", "data": node_state.get("phase_1")}
                elif node_name == "create_phase_2":
                    yield {"status": "creating_phase_2", "data": node_state.get("phase_2")}
                elif node_name == "create_phase_3":
                    yield {"status": "creating_phase_3", "data": node_state.get("phase_3")}
                elif node_name == "create_phase_4":
                    yield {"status": "creating_phase_4", "data": node_state.get("phase_4")}
                elif node_name == "create_resolution":
                    yield {"status": "creating_resolution", "data": node_state.get("resolution")}
                elif node_name == "create_rewards":
                    yield {"status": "creating_rewards", "data": node_state.get("rewards")}
                elif node_name == "compile_quest":
                    yield {"status": "complete", "data": node_state.get("complete_quest")}
