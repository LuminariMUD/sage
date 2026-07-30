"""Primary LangChain chat service for Luminari Sage.

This service provides flexible, unified creative capabilities for the Luminari universe,
following LangChain best practices for tool calling and streaming.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from src.llm.langchain_helpers import get_chat_model
from src.security import public_error_message

from .chains.direct_answer import DirectAnswerChain
from .chains.retrieval import RetrievalChain
from .chains.unified_creative import UnifiedCreativeTool

logger = logging.getLogger(__name__)


class LangChainChatService:
    """Clean implementation following LangChain best practices."""

    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.7):
        """Initialize with proper configuration."""
        self.model_name = model_name
        self.temperature = temperature

        # Initialize core components
        self.retrieval = RetrievalChain()
        self.direct_answer = DirectAnswerChain(enable_reflection=False)
        self.creative = UnifiedCreativeTool(model_name=model_name, temperature=temperature)

        # Create LLM with tools bound using provider abstraction
        self.llm = get_chat_model(
            task="chat", temperature=self.temperature, streaming=True, max_tokens=4000
        )
        self.llm_with_tools = self.llm.bind_tools(self._get_tools())

        # System prompt
        self.system_prompt = """You are the Luminari Sage, a creative and knowledgeable guide to the world of LuminariMUD.

YOUR PURPOSE:
Help users with ANY need related to the Luminari universe - from answering lore questions to creating epic questlines,
from developing new characters to writing stories, from describing locations to designing magical items.

KEY PRINCIPLES:
1. FLEXIBILITY: Adapt to what the user needs without forcing rigid categories
2. QUALITY: Default to rich, detailed output unless brevity is requested
3. CONTEXT: Remember everything from our conversation - never ask for what you already know
4. CREATIVITY: Support both canon-compliant and imaginative storytelling

TOOL USAGE RULES:
- ALWAYS search_lore FIRST before creating any content to ensure canon accuracy
- When calling create_content, the requirements parameter MUST be a dictionary like:
  {"premise": "the main idea", "setting": "where it happens", "tone": "epic/casual/dark"}
- Do NOT pass strings or lists to requirements - always use a dictionary
- When users ask to modify content you JUST created, you HAVE that content - don't ask for it
- Call each tool ONCE per request unless you need to gather more information
- After getting results from tools, provide the final answer - don't keep calling tools

QUALITY STANDARDS:
- Maintain quality throughout multi-part creations (no degradation in later parts)
- Use specific names and details from the lore, not generic placeholders
- Be efficient - don't call the same tool multiple times with the same parameters

Be creative, be helpful, and bring the world of Luminari to life!"""

    def _get_tools(self):
        """Define tools using proper LangChain patterns."""

        @tool
        async def search_lore(query: str) -> dict[str, Any]:
            """Search the Luminari lore knowledge base for canonical information.

            Args:
                query: What to search for

            Returns:
                Canonical lore facts and context blocks
            """
            result = await self.retrieval.ainvoke({"query": query})

            raw_data = result.get("raw", {})
            entities_count = len(raw_data.get("entities", [])) if raw_data else 0
            chunks_count = len(raw_data.get("chunks", [])) if raw_data else 0

            return {
                "context_blocks": result.get("context_blocks", []),
                "found_entities": entities_count,
                "found_chunks": chunks_count,
            }

        @tool
        async def answer_question(question: str, context_blocks: list[str] | None = None) -> str:
            """Provide a comprehensive answer about Luminari lore.

            Args:
                question: The question to answer
                context_blocks: Optional context from previous search

            Returns:
                Detailed answer based on canonical lore
            """
            if not context_blocks:
                retrieval_result = await self.retrieval.ainvoke({"query": question})
                context_blocks = retrieval_result.get("context_blocks", [])

            result = self.direct_answer.invoke(
                {"query": question, "context_blocks": context_blocks}
            )
            return result.get("answer", "I could not find information about that in the archives.")

        @tool
        async def create_content(
            content_type: str,
            requirements: dict[str, Any],
            context_blocks: list[str] | None = None,
        ) -> dict[str, Any]:
            """Create any type of content for the Luminari universe.

            Args:
                content_type: What to create (quest, questline, character, story, etc.)
                requirements: A dictionary containing your specific needs, for example:
                    {"premise": "the story idea", "length": "short/medium/long", "style": "epic/casual"}
                context_blocks: Optional lore context from search_lore

            Returns:
                Generated content with the structure and any metadata
            """
            logger.info(
                "Creating %s with %d characters of requirements",
                content_type,
                len(requirements),
            )

            try:
                result = await self.creative.create_content(
                    content_type=content_type, requirements=requirements, context=context_blocks
                )

                logger.info(f"Successfully created {content_type}")
                return result

            except Exception as e:
                logger.error("Content creation failed (%s)", type(e).__name__)
                return {
                    "error": public_error_message("Content creation"),
                    "type": content_type,
                    "requirements": requirements,
                }

        return [search_lore, answer_question, create_content]

    async def stream_chat(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ):
        """Stream chat responses using proper LangChain patterns.

        This implementation follows the LangChain recommended approach for
        tool calling with streaming.

        Args:
            message: User's message
            conversation_history: Previous messages

        Yields:
            Event dictionaries compatible with the API
        """
        # Build conversation messages
        messages = [SystemMessage(content=self.system_prompt)]

        if conversation_history:
            for msg in conversation_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=message))

        # Tool calling loop - increased for complex tasks but with better monitoring
        max_iterations = 10
        iteration = 0
        tool_call_history = []  # Track what tools have been called

        try:
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Processing iteration {iteration}")

                # Get response from LLM
                response = await self.llm_with_tools.ainvoke(messages)

                # Stream the content if there is any
                if response.content:
                    yield {"type": "content", "content": response.content}

                # Check if there are tool calls
                if response.tool_calls:
                    logger.info(
                        f"Iteration {iteration}: Executing {len(response.tool_calls)} tool calls"
                    )

                    # Track tool calls to detect loops
                    current_tools = [
                        (tc["name"], str(tc["args"])[:100]) for tc in response.tool_calls
                    ]
                    tool_call_history.append(current_tools)

                    # Check for repeated patterns (potential loop)
                    if len(tool_call_history) > 2:
                        if tool_call_history[-1] == tool_call_history[-2]:
                            logger.error("Detected repeated tool call pattern - potential loop!")
                            yield {
                                "type": "error",
                                "content": "Detected a loop in tool calling. Stopping to prevent timeout.",
                            }
                            break

                    # Add the assistant message with tool calls
                    messages.append(response)

                    # Execute each tool call
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_id = tool_call["id"]

                        logger.info("Executing tool %s", tool_name)

                        # Send tool status with args for debugging
                        yield {
                            "type": "tool_call",
                            "tool": tool_name,
                            "status": f"Executing {tool_name}...",
                        }

                        # Execute the tool
                        try:
                            # Get the tool by name
                            tools_by_name = {t.name: t for t in self._get_tools()}
                            if tool_name in tools_by_name:
                                tool_func = tools_by_name[tool_name]

                                # Fix parameters if needed
                                if tool_name == "create_content":
                                    # Ensure requirements is a dict
                                    if "requirements" not in tool_args:
                                        tool_args["requirements"] = {}
                                    elif not isinstance(tool_args["requirements"], dict):
                                        logger.warning(
                                            f"Requirements is not a dict: {type(tool_args['requirements'])}"
                                        )
                                        tool_args["requirements"] = {
                                            "content": str(tool_args["requirements"])
                                        }

                                # Invoke the tool
                                if hasattr(tool_func, "ainvoke"):
                                    result = await tool_func.ainvoke(tool_args)
                                else:
                                    result = await tool_func.func(**tool_args)

                                # Add tool result as message
                                from langchain_core.messages import ToolMessage

                                tool_message = ToolMessage(
                                    content=(
                                        json.dumps(result)
                                        if not isinstance(result, str)
                                        else result
                                    ),
                                    tool_call_id=tool_id,
                                )
                                messages.append(tool_message)

                                logger.info(f"Tool {tool_name} completed successfully")
                            else:
                                # Tool not found
                                from langchain_core.messages import ToolMessage

                                error_message = ToolMessage(
                                    content=f"Tool {tool_name} not found", tool_call_id=tool_id
                                )
                                messages.append(error_message)
                                logger.error(f"Tool {tool_name} not found")

                        except Exception as e:
                            logger.error("Tool execution failed (%s)", type(e).__name__)
                            from langchain_core.messages import ToolMessage

                            error_message = ToolMessage(
                                content=public_error_message("Tool execution"),
                                tool_call_id=tool_id,
                            )
                            messages.append(error_message)

                    # Continue to next iteration for final response
                    continue

                else:
                    # No tool calls, we're done
                    logger.info("Conversation complete")
                    break

            # Check if we hit max iterations
            if iteration >= max_iterations:
                logger.warning(
                    f"Hit maximum iterations ({max_iterations}) - this is likely a loop in tool calling"
                )
                yield {
                    "type": "error",
                    "content": (
                        f"Processing took too long after {max_iterations} iterations. "
                        "The agent may be stuck in a loop."
                    ),
                }

        except Exception as e:
            logger.error("Error in stream_chat (%s)", type(e).__name__)
            yield {"type": "error", "content": public_error_message("Chat stream")}

    async def chat(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """Non-streaming chat method for compatibility.

        Args:
            message: User's message
            conversation_history: Previous messages

        Returns:
            Complete response
        """
        full_response = ""
        tool_calls = []
        errors = []

        async for event in self.stream_chat(message, conversation_history):
            if event["type"] == "content":
                full_response += event["content"]
            elif event["type"] == "tool_call":
                tool_calls.append(event)
            elif event["type"] == "error":
                errors.append(event["content"])

        return {
            "answer": full_response,
            "tool_calls": tool_calls,
            "errors": errors or None,
        }
