"""DEPRECATED: Legacy keyword-based chat service for Luminari Sage.

This is the original implementation using keyword routing and classification.
Kept for backward compatibility only - use chat_service.py for new code.

Legacy approach:
- classify message
- run retrieval + appropriate chain
- return structured result
"""

from __future__ import annotations

import logging
from typing import Any

from .chains.direct_answer import DirectAnswerChain
from .chains.retrieval import RetrievalChain
from .util.classifier import classify, llm_classify

# Legacy chains removed during cleanup - service is deprecated
# from .chains.quest_planner import QuestPlannerChain
# from .chains.narrative import NarrativeChain
# from .chains.story_development import StoryDevelopmentChain
# from .chains.agent_orchestrator import AgentOrchestrator
# from .chains.questline_react import QuestlineReActAgent

logger = logging.getLogger(__name__)


class LangChainChatService:
    def __init__(self, enable_reflection: bool = True):
        """Initialize service with optional reflection.

        Args:
            enable_reflection: Whether to enable reflection for answer quality and plan validation
        """
        self.enable_reflection = enable_reflection
        self.retrieval = RetrievalChain()
        self.direct = DirectAnswerChain(enable_reflection=enable_reflection)
        # Legacy chains removed - using simplified fallback responses
        self.quest = None
        self.narrative = None
        self.story = None

        # Initialize ReAct agent for complex questlines
        self.questline_agent = None  # Lazy initialization to avoid import issues

        # Orchestrator disabled - chains removed
        self.orchestrator = None

    async def chat(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        # Use LLM classification if possible, fallback to heuristic
        try:
            route, confidence = await llm_classify(message, conversation_history)
        except Exception:
            route, confidence = classify(message)

        # For now only direct answer route implemented; others return TODO.
        retrieval_result = await self.retrieval.ainvoke({"query": message})

        # Add conversation history to the input if provided
        if conversation_history:
            retrieval_result["conversation_history"] = conversation_history

        if route == "orchestrated":
            # Orchestrator removed - fall back to lore_query
            route = "lore_query"

        if route == "lore_query":
            answer = self.direct.invoke(retrieval_result)
            return {"engine": "langchain", "route": route, "confidence": confidence, **answer}
        if route == "quest_planning":
            # Quest planner removed - provide fallback
            return {
                "engine": "langchain",
                "route": route,
                "confidence": confidence,
                "answer": "Quest planning is now handled by the modern unified service. Please use the updated API.",
                "plan": {},
            }
        if route == "narrative_generation":
            # Narrative chain removed - provide fallback
            return {
                "engine": "langchain",
                "route": route,
                "confidence": confidence,
                "answer": "Narrative generation is now handled by the modern unified service. Please use the updated API.",
            }
        if route == "story_development":
            # Story development removed - provide fallback
            return {
                "engine": "langchain",
                "route": route,
                "confidence": confidence,
                "answer": "Story development is now handled by the modern unified service. Please use the updated API.",
                "story_development": {},
            }
        # meta_help route
        return {
            "engine": "langchain",
            "route": route,
            "confidence": confidence,
            "answer": (
                "Supported modes: lore_query (factual answer), quest_planning (structured phases), "
                "narrative_generation (canon prose), story_development (new non-canon stories), "
                "questline_generation (multi-quest storylines with ReAct), "
                "meta_help (this message). Use descriptive verbs to trigger specialization."
            ),
        }

    def invoke(self, input: dict[str, Any]) -> dict[str, Any]:
        """Synchronous invoke for compatibility with orchestrator.

        This is called when the orchestrator selects the generate_questline tool.
        """
        import asyncio

        # Extract parameters
        query = input.get("query", "")

        # Try to extract number of quests from the input
        num_quests = 4  # Default

        # Check if num_quests is explicitly provided
        if "num_quests" in input:
            try:
                num_quests = int(input["num_quests"])
            except (ValueError, TypeError):
                num_quests = 4
        else:
            # Try to extract from query
            import re

            match = re.search(r"\b(\d+)\s*quests?\b", query, re.IGNORECASE)
            if match:
                num_quests = int(match.group(1))

        # Run async method synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                self._handle_questline(query, num_quests, input.get("conversation_history"))
            )
            return result
        finally:
            loop.close()

    async def ainvoke(self, input: dict[str, Any]) -> dict[str, Any]:
        """Async invoke for questline generation."""
        query = input.get("query", "")
        num_quests = input.get("num_quests", 4)

        # Try to parse num_quests if it's a string
        if isinstance(num_quests, str):
            try:
                num_quests = int(num_quests)
            except ValueError:
                num_quests = 4

        return await self._handle_questline(query, num_quests, input.get("conversation_history"))

    async def _handle_questline(
        self,
        message: str,
        num_quests: int,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Handle questline generation - fallback since chains removed.

        Args:
            message: User's request
            num_quests: Number of quests to generate
            conversation_history: Previous conversation

        Returns:
            Formatted response with questline
        """
        # Questline agent removed - provide fallback
        return {
            "engine": "langchain",
            "route": "questline_generation",
            "confidence": 0.5,
            "answer": "Questline generation is now handled by the modern unified service with ReAct support. Please use the updated API.",
            "error": "Legacy questline chains removed",
        }

    async def stream_chat(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ):  # async generator yielding events
        """Stream tokens/events for a chat message.

        Events:
          {type: 'route', route, confidence}
          {type: 'token', content: str}
          {type: 'final', answer, used_blocks, route, confidence}
          For non-token-streamed routes (quest/narrative/meta) we emit route then final only.
        """
        # Use LLM classification if possible, fallback to heuristic
        try:
            route, confidence = await llm_classify(message, conversation_history)
        except Exception:
            route, confidence = classify(message)
        retrieval_result = await self.retrieval.ainvoke({"query": message})
        blocks = retrieval_result.get("context_blocks", [])

        # Route announcement
        yield {"type": "route", "route": route, "confidence": confidence, "engine": "langchain"}

        if route == "orchestrated":
            # Orchestrator removed - fall back to lore_query
            route = "lore_query"

        if route == "lore_query":
            answer = self.direct.invoke(
                {
                    "query": message,
                    "context_blocks": blocks,
                    "conversation_history": conversation_history,
                }
            )
            content = answer.get("answer", "")
            if content:
                yield {"type": "token", "content": content, "engine": "langchain"}
            yield {
                "type": "final",
                "answer": content,
                "used_blocks": answer.get("used_blocks", len(blocks)),
                "route": route,
                "confidence": confidence,
                "engine": "langchain",
            }
            return

        # Non-streaming routes fallback
        if route == "quest_planning":
            # Quest planner removed - provide fallback
            yield {
                "type": "final",
                "answer": "Quest planning is now handled by the modern unified service. Please use the updated API.",
                "route": route,
                "confidence": confidence,
                "engine": "langchain",
            }
            return
        if route == "narrative_generation":
            # Narrative chain removed - provide fallback
            yield {
                "type": "final",
                "answer": "Narrative generation is now handled by the modern unified service. Please use the updated API.",
                "route": route,
                "confidence": confidence,
                "engine": "langchain",
            }
            return
        if route == "story_development":
            # Story development removed - provide fallback
            yield {
                "type": "final",
                "answer": "Story development is now handled by the modern unified service. Please use the updated API.",
                "story_development": {},
                "route": route,
                "confidence": confidence,
                "engine": "langchain",
            }
            return
        # meta_help
        yield {
            "type": "final",
            "answer": (
                "Supported modes: lore_query (streamed factual answer), quest_planning (structured phases), "
                "narrative_generation (canon prose), story_development (new non-canon stories), "
                "meta_help (this message)."
            ),
            "route": route,
            "confidence": confidence,
            "engine": "langchain",
        }
