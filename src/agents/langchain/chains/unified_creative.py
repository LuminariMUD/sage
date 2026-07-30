"""Unified Creative Tool for flexible content generation.

This single tool replaces multiple specialized tools and adapts to any creative need,
maintaining quality while allowing maximum flexibility.
"""

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from src.llm.langchain_helpers import get_chat_model
from src.security import public_error_message

logger = logging.getLogger(__name__)


class UnifiedCreativeTool:
    """A flexible creative tool that adapts to any content generation need."""

    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.7):
        # Use creative task for content generation with provider abstraction
        self.llm = get_chat_model(
            task="creative", temperature=temperature, streaming=False, max_tokens=4000
        )

    async def create_content(
        self, content_type: str, requirements: dict[str, Any], context: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Generate any type of creative content based on requirements.

        Args:
            content_type: Type of content (quest, questline, story, character, narrative, etc.)
            requirements: Flexible requirements dict that can contain:
                - premise/concept: The main idea
                - quality_level: brief/standard/detailed/epic
                - constraints: Any specific requirements
                - previous_content: Content to build upon
                - Any other parameters specific to the content type
            context: Optional lore context from searches

        Returns:
            Generated content with metadata
        """

        # Build the context section
        context_section = ""
        if context:
            context_section = "\n\nRelevant Lore Context:\n" + "\n".join(context)

        # Build requirements section
        req_lines = []
        for key, value in requirements.items():
            if value is not None:
                req_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        requirements_section = "\n".join(req_lines)

        # Create a flexible prompt that adapts to the content type
        system_prompt = """You are the Luminari Sage, a master storyteller and world-builder for the LuminariMUD universe.

Your task is to create {content_type} content that:
1. Respects and builds upon canonical lore when provided
2. Meets all specified requirements exactly
3. Maintains consistent quality throughout
4. Provides rich, detailed content unless brevity is specifically requested

Important Guidelines:
- If creating quests: Include specific NPCs, locations, and detailed phase descriptions
- If creating stories: Develop compelling narratives with clear character arcs
- If creating characters: Provide rich backstories and clear motivations
- If creating narratives: Focus on atmospheric description and emotional resonance
- If creating questlines: Maintain continuity and quality across all connected pieces

Quality Standards:
- Default to rich, detailed descriptions unless told otherwise
- Use specific names rather than generic terms
- Include sensory details and emotional elements
- Maintain the quality level throughout (no degradation in later sections)
- If a minimum word count is specified, meet or exceed it consistently"""

        human_prompt = """Create {content_type} with these specifications:

{requirements_section}
{context_section}

Generate the content now. Ensure it fully addresses all requirements and maintains consistent quality throughout."""

        # Format the prompts
        formatted_system = system_prompt.format(content_type=content_type)
        formatted_human = human_prompt.format(
            content_type=content_type,
            requirements_section=requirements_section,
            context_section=context_section,
        )

        try:
            # Create the prompt template
            prompt = ChatPromptTemplate.from_messages(
                [("system", formatted_system), ("human", formatted_human)]
            )

            # Generate the content
            response = await self.llm.ainvoke(prompt.format_prompt().to_messages())
            content = response.content

            # Try to parse as JSON if it looks like JSON
            try:
                if content.strip().startswith("{") or content.strip().startswith("["):
                    parsed_content = json.loads(content)
                else:
                    parsed_content = {"content": content}
            except json.JSONDecodeError:
                parsed_content = {"content": content}

            # Add metadata
            # Get model name - ChatOpenAI uses model_name, ChatOllama uses model
            model_identifier = getattr(self.llm, "model_name", None) or getattr(
                self.llm, "model", "unknown"
            )
            result = {
                "type": content_type,
                "requirements_met": requirements,
                "data": parsed_content,
                "metadata": {"model": model_identifier, "had_context": bool(context)},
            }

            logger.info(f"Successfully generated {content_type} content")
            return result

        except Exception as e:
            logger.error("Failed to generate %s (%s)", content_type, type(e).__name__)
            return {
                "type": content_type,
                "error": public_error_message("Content generation"),
                "data": None,
            }

    async def enhance_content(
        self,
        original_content: Any,
        enhancement_type: str,
        specific_requirements: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Enhance or modify existing content.

        Args:
            original_content: The content to enhance
            enhancement_type: Type of enhancement (expand, improve_quality, add_detail, fix_issues)
            specific_requirements: Specific things to enhance

        Returns:
            Enhanced content
        """
        requirements = {"original_content": original_content, "enhancement_type": enhancement_type}

        if specific_requirements:
            requirements.update(specific_requirements)

        return await self.create_content(
            content_type=f"enhanced_{enhancement_type}", requirements=requirements
        )

    async def combine_content(
        self,
        content_pieces: list[Any],
        combination_type: str = "merge",
        requirements: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Combine multiple pieces of content into a cohesive whole.

        Args:
            content_pieces: List of content to combine
            combination_type: How to combine (merge, sequence, interweave)
            requirements: Additional requirements for combination

        Returns:
            Combined content
        """
        combo_requirements = {
            "content_pieces": content_pieces,
            "combination_type": combination_type,
        }

        if requirements:
            combo_requirements.update(requirements)

        return await self.create_content(
            content_type="combined_content", requirements=combo_requirements
        )


# Convenience functions for common content types
async def create_quest(premise: str, **kwargs) -> dict[str, Any]:
    """Create a single quest."""
    tool = UnifiedCreativeTool()
    requirements = {"premise": premise}
    requirements.update(kwargs)
    return await tool.create_content("quest", requirements)


async def create_questline(premise: str, num_quests: int = 4, **kwargs) -> dict[str, Any]:
    """Create a connected questline."""
    tool = UnifiedCreativeTool()
    requirements = {
        "premise": premise,
        "num_quests": num_quests,
        "maintain_quality": True,
        "ensure_continuity": True,
    }
    requirements.update(kwargs)
    return await tool.create_content("questline", requirements)


async def create_story(concept: str, **kwargs) -> dict[str, Any]:
    """Create a story or narrative."""
    tool = UnifiedCreativeTool()
    requirements = {"concept": concept}
    requirements.update(kwargs)
    return await tool.create_content("story", requirements)


async def create_character(name: str, role: str, **kwargs) -> dict[str, Any]:
    """Create a character with backstory."""
    tool = UnifiedCreativeTool()
    requirements = {"name": name, "role": role}
    requirements.update(kwargs)
    return await tool.create_content("character", requirements)
