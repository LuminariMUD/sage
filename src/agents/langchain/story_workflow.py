"""Story building workflow for structured narrative generation."""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from src.llm.langchain_helpers import get_chat_model

logger = logging.getLogger(__name__)


def _extract_json_content(raw: str) -> dict[str, Any]:
    """Pull JSON payload out of common markdown wrappers."""

    text = raw.strip() if raw else ""
    if not text:
        return {}

    for fence in ("```json", "```JSON", "```"):
        if fence in text:
            try:
                segment = text.split(fence, 1)[1]
            except IndexError:
                continue
            if "```" in segment:
                segment = segment.split("```", 1)[0]
            text = segment.strip()
            break

    try:
        return json.loads(text)
    except Exception as exc:  # pragma: no cover - fallback
        logger.warning("Failed to parse JSON content (%s)", type(exc).__name__)
        return {}


class StoryState(TypedDict):
    """State representation for the story workflow."""

    requirements: str
    lore_context: list[str]
    story_length: str
    story_brief: dict[str, Any]
    section_plan: list[dict[str, Any]]
    section_index: int
    sections: list[dict[str, Any]]
    complete_story: dict[str, Any]


class StoryWorkflow:
    """Structured workflow that produces multi-section stories."""

    def __init__(self, model_planning: str = "gpt-4.1", model_writing: str = "gpt-4o") -> None:
        # Use reasoning task for story planning (lower temperature)
        self.brief_llm = get_chat_model(task="reasoning", temperature=0.6, streaming=False)
        # Use creative task for story writing (higher temperature)
        self.section_llm = get_chat_model(task="creative", temperature=0.85, streaming=False)
        self.graph = self._build_graph()
        self.app = self.graph.compile()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(StoryState)

        graph.add_node("create_brief", self._create_brief)
        graph.add_node("generate_section", self._generate_section)
        graph.add_node("compile_story", self._compile_story)

        graph.set_entry_point("create_brief")
        graph.add_edge("create_brief", "generate_section")
        graph.add_conditional_edges(
            "generate_section",
            self._has_more_sections,
            {
                "continue": "generate_section",
                "done": "compile_story",
            },
        )
        graph.add_edge("compile_story", END)
        return graph

    async def build_story(
        self,
        requirements: str,
        lore_context: list[str] | None = None,
        story_length: str = "medium",
    ) -> dict[str, Any]:
        """Run the workflow and return the structured story payload."""

        initial_state: StoryState = {
            "requirements": requirements,
            "lore_context": lore_context or [],
            "story_length": story_length,
            "story_brief": {},
            "section_plan": [],
            "section_index": 0,
            "sections": [],
            "complete_story": {},
        }

        result = await self.app.ainvoke(initial_state)
        return result["complete_story"]

    async def _create_brief(self, state: StoryState) -> StoryState:
        """Create the story brief, cast, and section plan."""

        lore_lines = "\n".join(f"- {item}" for item in state["lore_context"][:12]) or "- None"
        prompt = f"""You are a narrative architect for the Luminari universe.

Create a detailed story blueprint from the user's request and the canonical lore.

User Request:
{state["requirements"]}

Canonical Lore:
{lore_lines}

Desired Length: {state["story_length"]} (short = 3 sections, medium = 4-5, epic = 6-7).

Return JSON with the following structure:
{{
  "title": "...",
  "synopsis": "...",
  "tone": "...",
  "themes": ["..."],
  "length": {{
      "target_sections": int,
      "target_paragraphs_per_section": int,
      "dialogue_emphasis": "low/medium/high"
  }},
  "characters": [
      {{"name": "...", "role": "protagonist/supporting/antagonist", "motivation": "..."}}
  ],
  "section_plan": [
      {{"name": "...", "focus": "...", "summary_goal": "...", "paragraphs": int}}
  ],
  "lore_threads": ["key canon beats to reinforce"]
}}
"""

        response = await self.brief_llm.ainvoke([HumanMessage(content=prompt)])
        brief = _extract_json_content(response.content)
        if not brief:
            brief = {
                "title": "Untitled Tale of Lumia",
                "synopsis": state["requirements"][:200],
                "tone": "narrative",
                "themes": [],
                "length": {
                    "target_sections": 4,
                    "target_paragraphs_per_section": 3,
                    "dialogue_emphasis": "medium",
                },
                "characters": [],
                "section_plan": [
                    {
                        "name": "Opening",
                        "focus": "Introduce protagonists",
                        "summary_goal": "Set the stage",
                        "paragraphs": 3,
                    },
                    {
                        "name": "Rising Action",
                        "focus": "Escalate conflict",
                        "summary_goal": "Complicate the quest",
                        "paragraphs": 3,
                    },
                    {
                        "name": "Climax",
                        "focus": "Highest tension",
                        "summary_goal": "Resolve conflict",
                        "paragraphs": 3,
                    },
                    {
                        "name": "Resolution",
                        "focus": "Aftermath",
                        "summary_goal": "Show consequences",
                        "paragraphs": 2,
                    },
                ],
                "lore_threads": [],
            }

        section_plan = brief.get("section_plan") or []
        if not section_plan:
            target_sections = brief.get("length", {}).get("target_sections", 4)
            section_plan = [
                {
                    "name": f"Section {i + 1}",
                    "focus": "Progress the story",
                    "summary_goal": "",
                    "paragraphs": brief.get("length", {}).get("target_paragraphs_per_section", 3),
                }
                for i in range(target_sections)
            ]

        state["story_brief"] = brief
        state["section_plan"] = section_plan
        state["section_index"] = 0
        return state

    def _has_more_sections(self, state: StoryState) -> str:
        if state["section_index"] < len(state["section_plan"]):
            return "continue"
        return "done"

    async def _generate_section(self, state: StoryState) -> StoryState:
        """Generate the next story section according to the plan."""

        index = state["section_index"]
        plan = state["section_plan"][index]
        brief = state["story_brief"]
        previous_text = "\n\n".join(section["text"] for section in state["sections"]) or "<none>"
        lore_snippets = "\n".join(f"- {item}" for item in state["lore_context"][:12]) or "- None"

        prompt = f"""You are writing a canon-respectful story in the Luminari universe.

Story Title: {brief.get("title", "Untitled Tale")}
Synopsis: {brief.get("synopsis", "")}
Tone: {brief.get("tone", "narrative")}
Themes: {", ".join(brief.get("themes", []))}
Key Lore Threads: {", ".join(brief.get("lore_threads", []))}

Existing Story So Far:
{previous_text}

Lore References:
{lore_snippets}

Current Section Goal:
- Name: {plan.get("name", f"Section {index + 1}")}
- Focus: {plan.get("focus", "")}
- Summary Goal: {plan.get("summary_goal", "")}
- Target Paragraphs: {plan.get("paragraphs", 3)}
- Dialogue Emphasis: {brief.get("length", {}).get("dialogue_emphasis", "medium")}

Characters:
{json.dumps(brief.get("characters", []), ensure_ascii=False)}

Write this section, ensuring continuity and canon fidelity. Use paragraphs (NOT bullet points) and weave in dialogue or introspection as appropriate.
Return JSON:
{{
  "section_name": "...",
  "summary": "...",
  "text": "...",
  "paragraph_count": int
}}
"""

        response = await self.section_llm.ainvoke([HumanMessage(content=prompt)])
        payload = _extract_json_content(response.content)
        if not payload:
            payload = {
                "section_name": plan.get("name", f"Section {index + 1}"),
                "summary": plan.get("summary_goal", ""),
                "text": response.content,
                "paragraph_count": plan.get("paragraphs", 3),
            }

        state["sections"].append(payload)
        state["section_index"] += 1
        return state

    async def _compile_story(self, state: StoryState) -> StoryState:
        """Assemble the final structured payload."""

        brief = state["story_brief"]
        sections = state["sections"]
        full_text = "\n\n".join(section.get("text", "") for section in sections).strip()

        state["complete_story"] = {
            "title": brief.get("title", "Untitled Tale"),
            "synopsis": brief.get("synopsis", ""),
            "tone": brief.get("tone", "narrative"),
            "themes": brief.get("themes", []),
            "length": brief.get("length", {}),
            "characters": brief.get("characters", []),
            "section_plan": brief.get("section_plan", []),
            "sections": sections,
            "full_story": full_text,
            "lore_threads": brief.get("lore_threads", []),
            "lore_context_used": state["lore_context"],
        }
        return state
