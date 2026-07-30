"""Reflection chain for evaluating and improving responses.

Focuses on:
1. Fact-checking against retrieved context
2. Identifying gaps in context that need additional retrieval
3. Validating plans and tool sequences
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from src.llm.config import get_llm_provider_config
from src.llm.langchain_helpers import get_chat_model

logger = logging.getLogger(__name__)

# Reflection for fact-checking and context sufficiency
FACT_CHECK_PROMPT = """You are a critical reviewer evaluating an answer about LuminariMUD lore.

Your task is to:
1. Check if EVERY factual claim in the answer is supported by the provided context
2. Pay special attention to:
   - Racial/cultural attributes (languages, abilities, customs)
   - Names and titles
   - Historical events and dates
   - Relationships between entities
3. Identify any claims not explicitly supported by the context
4. Determine if more context is needed for accuracy
5. Suggest specific queries for additional retrieval if needed

Context blocks provided:
{context}

Question asked:
{question}

Generated answer:
{answer}

Evaluate this answer and return a JSON response with this structure:
{{
  "is_grounded": true/false,
  "unsupported_claims": ["list of specific claims not found in context"],
  "context_sufficient": true/false,
  "missing_aspects": ["what information is missing to verify claims"],
  "suggested_queries": ["specific search queries to verify unsupported claims"],
  "confidence_score": 0.0-1.0,
  "reasoning": "brief explanation of issues found"
}}

Be VERY strict - if the answer attributes ANY characteristic (language, ability, culture) to a race/entity that isn't explicitly stated in the context for THAT specific race/entity, mark it as unsupported.

Example: If context mentions "Crystal Dwarves speak Tal" but the answer says "Elves speak Tal", this is unsupported even though Tal is mentioned in context."""

# Reflection for plan validation
PLAN_VALIDATION_PROMPT = """You are reviewing an execution plan for a user request.

Evaluate if the plan:
1. Uses the right tools in the right order
2. Has necessary dependencies between steps
3. Could be simplified
4. Will actually fulfill the user's request

User request: {request}

Proposed plan:
{plan}

Available tools:
- search_lore: Search for canonical lore information
- develop_story: Create new non-canon story elements
- plan_quest: Create structured quest/adventure
- generate_narrative: Write narrative prose from lore
- answer_lore: Direct answer about canonical lore

Return a JSON response:
{{
  "plan_valid": true/false,
  "issues": ["list of problems"],
  "suggestions": ["improvements"],
  "simplified_plan": null or [simplified step list],
  "confidence_score": 0.0-1.0
}}"""


class ReflectionResult(BaseModel):
    """Result of reflection evaluation"""

    is_grounded: bool = Field(default=True, description="Whether answer is grounded in context")
    unsupported_claims: list[str] = Field(
        default_factory=list, description="Claims not supported by context"
    )
    context_sufficient: bool = Field(default=True, description="Whether context is adequate")
    missing_aspects: list[str] = Field(default_factory=list, description="Information gaps")
    suggested_queries: list[str] = Field(
        default_factory=list, description="Queries for additional retrieval"
    )
    confidence_score: float = Field(default=1.0, description="Confidence in the answer")
    reasoning: str = Field(default="", description="Explanation of evaluation")
    needs_revision: bool = Field(default=False, description="Whether answer needs revision")


class PlanReflectionResult(BaseModel):
    """Result of plan validation"""

    plan_valid: bool = Field(default=True)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    simplified_plan: list[dict[str, Any]] | None = None
    confidence_score: float = Field(default=1.0)


def _format_context_blocks(blocks: list[str]) -> str:
    if not blocks:
        return "No context provided"
    return "\n".join(f"[Block {idx}] {block}" for idx, block in enumerate(blocks))


class ReflectionChain(Runnable):
    """Chain for reflecting on and improving responses."""

    def __init__(self, model_name: str = "gpt-4.1", temperature: float = 0.0):
        """Initialize with low temperature for consistent evaluation."""
        self.llm = None

        # Get provider config to determine if we should use real LLM
        config = get_llm_provider_config()
        provider = config["provider"]

        # Ollama always available (local), OpenAI needs API key
        use_real_llm = (provider == "ollama") or (
            provider == "openai" and os.getenv("OPENAI_API_KEY")
        )

        if use_real_llm:
            try:
                # Use reasoning task for reflection (fact-checking requires careful analysis)
                self.llm = get_chat_model(
                    task="reasoning", temperature=temperature, streaming=False
                )
            except Exception as e:
                logger.warning("Failed to initialize reflection LLM (%s)", type(e).__name__)

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract and parse JSON from LLM response."""
        text = text.strip()

        # Remove markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the text
            import re

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Return default safe response
        return {
            "is_grounded": True,
            "context_sufficient": True,
            "confidence_score": 0.5,
            "reasoning": "Could not parse reflection",
        }

    async def reflect_on_answer(
        self, answer: str, question: str, context_blocks: list[str]
    ) -> ReflectionResult:
        """Reflect on an answer's accuracy and completeness.

        Args:
            answer: The generated answer to evaluate
            question: The original question
            context_blocks: The context used to generate the answer

        Returns:
            ReflectionResult with evaluation details
        """
        if not self.llm:
            # No reflection without LLM
            return ReflectionResult()

        context = _format_context_blocks(context_blocks)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a strict fact-checker for a fantasy lore system."),
                ("human", FACT_CHECK_PROMPT),
            ]
        )

        try:
            formatted = prompt.format_prompt(context=context, question=question, answer=answer)

            response = await self.llm.ainvoke(formatted.to_messages())
            result_dict = self._parse_json_response(response.content)

            # Determine if revision is needed
            needs_revision = (
                not result_dict.get("is_grounded", True)
                or not result_dict.get("context_sufficient", True)
                or result_dict.get("confidence_score", 1.0) < 0.7
            )
            result_dict["needs_revision"] = needs_revision

            return ReflectionResult(**result_dict)

        except Exception as e:
            logger.error("Reflection failed (%s)", type(e).__name__)
            return ReflectionResult()

    async def reflect_on_plan(self, plan: dict[str, Any], request: str) -> PlanReflectionResult:
        """Validate an execution plan.

        Args:
            plan: The execution plan to validate
            request: The original user request

        Returns:
            PlanReflectionResult with validation details
        """
        if not self.llm:
            return PlanReflectionResult()

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a planning optimization expert."),
                ("human", PLAN_VALIDATION_PROMPT),
            ]
        )

        try:
            formatted = prompt.format_prompt(request=request, plan=json.dumps(plan, indent=2))

            response = await self.llm.ainvoke(formatted.to_messages())
            result_dict = self._parse_json_response(response.content)

            return PlanReflectionResult(**result_dict)

        except Exception as e:
            logger.error("Plan reflection failed (%s)", type(e).__name__)
            return PlanReflectionResult()

    def invoke(self, input: dict[str, Any], config: dict | None = None) -> dict[str, Any]:
        """Synchronous invoke for compatibility."""
        import asyncio

        reflection_type = input.get("type", "answer")

        if reflection_type == "answer":
            answer = input.get("answer", "")
            question = input.get("question", "")
            context_blocks = input.get("context_blocks", [])

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.reflect_on_answer(answer, question, context_blocks)
                )
                return result.dict()
            finally:
                loop.close()

        elif reflection_type == "plan":
            plan = input.get("plan", {})
            request = input.get("request", "")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.reflect_on_plan(plan, request))
                return result.dict()
            finally:
                loop.close()

        return {"error": "Unknown reflection type"}
