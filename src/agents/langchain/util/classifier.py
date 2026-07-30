"""Classifier for routing chat requests to specialized chains.

Strategy: LLM-based classification with heuristic fallback.
"""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate

from src.llm.langchain_helpers import get_chat_model

Route = Literal[
    "lore_query",
    "quest_planning",
    "narrative_generation",
    "story_development",
    "orchestrated",
    "questline_generation",
    "meta_help",
]

QUEST_PATTERNS = re.compile(
    r"\b(quest|plan|arc|story ?arc|objective|phases|campaign)\b", re.IGNORECASE
)
QUESTLINE_PATTERNS = re.compile(
    r"\b(\d+\s*quests?|questline|quest\s*line|series\s*of\s*quests|connected\s*quests|quest\s*chain)\b",
    re.IGNORECASE,
)
NARRATIVE_PATTERNS = re.compile(
    r"\b(write|scene|narrative|prose|describe|story|dramatic)\b", re.IGNORECASE
)
STORY_DEV_PATTERNS = re.compile(
    r"\b(develop|create|new story|new character|new location|expand|imagine|what if|non-?canon|story idea|collaborate)\b",
    re.IGNORECASE,
)
ORCHESTRATION_PATTERNS = re.compile(
    r"\b(then|after that|based on|using that|followed by|and then|next|\d+\s*(quests?|stories|narratives|parts?|chapters?))\b",
    re.IGNORECASE,
)
META_PATTERNS = re.compile(r"\b(help|what can you do|capabilities|commands)\b", re.IGNORECASE)

# LLM Classification prompt
CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a message router for a Luminari lore assistant. Analyze the user's message and conversation context to determine the appropriate response type.

Routes:
- lore_query: Factual questions about the world, characters, events, or seeking information
- quest_planning: Requests to create A SINGLE quest, adventure, or story arc
- questline_generation: Requests for MULTIPLE CONNECTED quests (e.g., "4 quests", "questline", "series of quests")
- narrative_generation: Requests to write scenes, narratives, or creative prose from existing lore
- story_development: Requests to develop NEW stories, characters, locations, or expand the world beyond canon
- orchestrated: Complex requests requiring multiple different operations (e.g., "create a story THEN make a quest based on it")
- meta_help: Questions about capabilities or how to use the system

IMPORTANT:
- If the user asks for MULTIPLE QUESTS specifically, route to "questline_generation"
- If the user asks for multiple DIFFERENT things (story + quest), route to "orchestrated"
- "questline", "quest line", "4 quests", "series of quests" → questline_generation

Consider the conversation history to understand context. If someone asks "tell me more" or "what about X", consider what they were previously discussing.

Respond with ONLY the route name, nothing else.""",
        ),
        (
            "human",
            """Conversation history:
{history}

Current message: {message}

Route:""",
        ),
    ]
)


async def llm_classify(
    message: str, conversation_history: list[dict[str, str]] | None = None
) -> tuple[Route, float]:
    """Classify user message using LLM with conversation context.

    Returns (route, confidence). Confidence is 0.95 for LLM classification.
    """
    try:
        # Use provider abstraction with reasoning model (low temperature for classification)
        llm = get_chat_model(task="reasoning", temperature=0.1, streaming=False)

        # Format conversation history
        history_text = ""
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 6 messages for context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    history_text += (
                        f"{role}: {content[:200]}...\n"
                        if len(content) > 200
                        else f"{role}: {content}\n"
                    )

        if not history_text:
            history_text = "(No previous conversation)"

        # Get classification from LLM
        prompt = CLASSIFIER_PROMPT.format_prompt(history=history_text, message=message)
        response = await llm.ainvoke(prompt.to_messages())
        route_str = response.content.strip().lower()

        # Map response to route
        if "questline" in route_str:
            return ("questline_generation", 0.95)
        elif "orchestrated" in route_str:
            return ("orchestrated", 0.95)
        elif "quest" in route_str or "planning" in route_str:
            return ("quest_planning", 0.95)
        elif "narrative" in route_str or "generation" in route_str:
            return ("narrative_generation", 0.95)
        elif "story" in route_str or "development" in route_str:
            return ("story_development", 0.95)
        elif "meta" in route_str or "help" in route_str:
            return ("meta_help", 0.95)
        else:
            return ("lore_query", 0.95)

    except Exception:
        # Fallback to heuristic classification on any error
        return classify(message)


def classify(message: str) -> tuple[Route, float]:
    """Classify user message using heuristic patterns (fallback).

    Returns (route, confidence). Confidence is heuristic 0-1.
    """
    text = message.strip()
    if not text:
        return ("lore_query", 0.1)

    if META_PATTERNS.search(text):
        return ("meta_help", 0.85)

    # Check for questline patterns first
    if QUESTLINE_PATTERNS.search(text):
        return ("questline_generation", 0.95)

    # Check for numbered requests (e.g., "4 quests", "3 stories")
    import re

    numbered_match = re.search(
        r"\b(\d+)\s*(quests?|stories|narratives|parts?|chapters?)\b", text, re.IGNORECASE
    )
    if numbered_match and int(numbered_match.group(1)) > 1:
        # Multiple quests specifically → questline
        if "quest" in numbered_match.group(2).lower():
            return ("questline_generation", 0.95)
        # Other multiple items → orchestrated
        return ("orchestrated", 0.95)

    # Check for orchestration patterns combined with multiple operations
    has_orchestration = ORCHESTRATION_PATTERNS.search(text)
    has_story = STORY_DEV_PATTERNS.search(text)
    has_quest = QUEST_PATTERNS.search(text)
    has_narrative = NARRATIVE_PATTERNS.search(text)

    # Count how many different operations are mentioned
    operation_count = sum([bool(has_story), bool(has_quest), bool(has_narrative)])

    # If orchestration patterns and multiple operations, it needs orchestration
    if has_orchestration and operation_count >= 2:
        return ("orchestrated", 0.9)

    # Single operation routes
    if has_story:
        return ("story_development", 0.8)
    if has_quest:
        return ("quest_planning", 0.75)
    if has_narrative:
        return ("narrative_generation", 0.7)
    # default fallback
    return ("lore_query", 0.6)
