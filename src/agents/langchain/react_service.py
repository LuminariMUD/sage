"""THE ReAct Service - Stateful scratchpad with focused tools.

This is the definitive ReAct implementation combining:
- Stateful scratchpad from LangGraph for context maintenance
- Focused, single-purpose tools for efficiency
- Full transparency with streaming updates
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.llm.langchain_helpers import get_chat_model
from src.security import public_error_message

from .focused_tools import get_focused_tools
from .state_manager import get_state_manager

logger = logging.getLogger(__name__)


class ReActState(TypedDict):
    """State for ReAct agent with persistent scratchpad."""

    # Core conversation
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # THE SCRATCHPAD - maintains all reasoning and observations
    scratchpad: list[dict[str, Any]]

    # Context from lore searches
    context_blocks: list[str]

    # Whether a retrieval tool has actually run. Distinct from context_blocks being
    # non-empty: a search that legitimately finds nothing has still been performed, and
    # conflating the two deadlocks the fallback-search guard against loop detection.
    search_performed: bool

    # Content created so far (for quality maintenance)
    created_content: list[dict[str, Any]]

    # Current step info
    current_step: dict[str, Any] | None
    iteration_count: int
    max_iterations: int

    # Original request
    original_request: str

    # Tool history for loop detection
    tool_history: list[tuple]

    # Plan of attack for multi-step requests
    plan: list[dict[str, Any]] | None

    # High-level intent of the latest request (informational vs generative)
    request_intent: str

    # Cached story metadata for follow-up requests
    story_cache: dict[str, Any]


class ReactService:
    """THE ReAct service with scratchpad and focused tools."""

    def __init__(
        self,
        model_name: str = "gpt-4.1",
        temperature: float = 0.7,
        max_iterations: int = 20,  # More iterations for smaller tools
    ):
        """Initialize the ReAct service."""
        self.model_name = model_name
        self.temperature = temperature
        self.max_iterations = max_iterations

        # Initialize LLM with provider abstraction.
        # The ReAct loop binds tools, so this must be a tool-calling model. The "reasoning"
        # task maps to a chain-of-thought model (deepseek-r1 by default) whose output Ollama's
        # tool parser rejects with "does not match the expected peg-native format", failing
        # every tool call. "tools" resolves to a model that supports tool calling.
        # The ReAct graph streams its own reasoning/tool/final events; it does not
        # consume token chunks from this tool-selection request.  Some strict
        # OpenRouter routes (including Qwen 3.7 Flash) expose tools and streaming
        # independently but have no endpoint for the combined parameter set.
        # The same strict route also rejects tools combined with max_tokens.  A
        # ReAct decision emits only a tool call or ``finalize``, so it does not
        # need a generation cap; answer/content tools retain their own caps.
        # Keep the model call non-streaming so provider routing can select the
        # advertised tool-capable endpoint.
        self.llm = get_chat_model(
            task="tools",
            temperature=temperature,
            streaming=False,
            disable_streaming=True,
            reasoning_effort="none",
        )

        # Planner model keeps the roadmap focused (lower temperature)
        self.planner_llm = get_chat_model(
            task="reasoning", temperature=0.3, streaming=False, max_tokens=1500
        )

        # Get focused tools
        self.tools = get_focused_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Build the graph
        self.graph = self._build_graph()

        # Memory for conversation state
        self.memory = MemorySaver()

        # Compile the graph with memory
        self.app = self.graph.compile(checkpointer=self.memory)

        # Set recursion limit if supported
        if hasattr(self.app, "recursion_limit"):
            self.app.recursion_limit = 50

        # State manager for persistence
        self.state_manager = get_state_manager()

    def _infer_request_intent(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ) -> str:
        """Heuristically determine if the user wants information or generated content."""

        if not message:
            return "informational"

        text = message.lower()

        generative_nouns = {
            "quest",
            "questline",
            "npc",
            "npcs",
            "story",
            "stories",
            "narrative",
            "adventure",
            "mission",
            "encounter",
            "dialogue",
            "hook",
            "phase",
            "reward",
            "episode",
            "scene",
            "campaign",
        }
        creation_triggers = {
            "create",
            "generate",
            "write",
            "design",
            "craft",
            "build",
            "compose",
            "produce",
            "make",
            "plan",
            "draft",
            "invent",
            "come up with",
            "give me",
            "need a",
            "need another",
            "continue the",
            "continue this",
            "develop",
        }

        story_phrases = {
            "tell me a story",
            "spin a tale",
            "share a story",
            "story about",
            "extend that story",
            "extend the story",
            "add to the story",
            "continue that story",
            "longer story",
            "multi chapter",
            "multi-part story",
        }

        # Detect explicit creation style requests
        if any(trigger in text for trigger in creation_triggers):
            if any(noun in text for noun in generative_nouns):
                return "generative"

        if any(phrase in text for phrase in story_phrases):
            return "generative"

        # Detect short continuation commands referencing prior creative work
        short_message = text.strip()
        if short_message in {
            "continue",
            "continue story",
            "continue the story",
            "continue the quest",
            "extend that story",
            "extend the story",
            "more story",
            "more of the story",
        }:
            return "generative"

        # Recognize informational cues (questions, detail requests)
        informational_cues = {
            "who",
            "what",
            "where",
            "when",
            "why",
            "how",
            "tell me",
            "describe",
            "explain",
            "details",
            "detail",
            "information",
            "background",
            "history",
            "more about",
            "more details",
            "give me more",
        }
        if "?" in message or any(cue in text for cue in informational_cues):
            return "informational"

        # If the follow-up is very short but prior assistant spoke, assume informational clarification
        if conversation_history:
            if short_message in {"more", "more details", "details", "tell me more"}:
                return "informational"

        return "informational"

    def _build_graph(self) -> StateGraph:
        """Build the ReAct state graph."""

        graph = StateGraph(ReActState)

        # Add nodes
        graph.add_node("reason", self._reason_step)
        graph.add_node("act", self._act_step)
        graph.add_node("observe", self._observe_step)
        graph.add_node("decide", self._decide_step)
        graph.add_node("finalize", self._finalize_step)

        # Set entry point
        graph.set_entry_point("reason")

        # Add edges
        graph.add_edge("reason", "act")
        graph.add_edge("act", "observe")
        graph.add_edge("observe", "decide")

        # Conditional edges from decide
        graph.add_conditional_edges(
            "decide", self._should_continue, {"continue": "reason", "finalize": "finalize"}
        )

        # End from finalize
        graph.add_edge("finalize", END)

        return graph

    async def _reason_step(self, state: ReActState) -> dict[str, Any]:
        """Reasoning step: Determine next action based on scratchpad."""

        # Build reasoning context from scratchpad
        reasoning_context = self._build_reasoning_context(state)

        # Ensure we have a plan to follow for complex prompts
        await self._ensure_plan(state)
        self._update_plan_progress(state)
        plan_text = self._format_plan(state)

        # Surface relevant lore and recent generations for grounding
        lore_preview = self._format_context_preview(state)
        recent_content = self._format_recent_content(state)

        # Add conversation context if there are previous messages
        conversation_context = ""
        if len(state["messages"]) > 1:
            conversation_context = "RECENT CONVERSATION:\n"
            for msg in state["messages"][-4:-1]:  # Show last 3 messages before current
                if isinstance(msg, HumanMessage):
                    conversation_context += (
                        f"User: {msg.content[:200]}...\n"
                        if len(msg.content) > 200
                        else f"User: {msg.content}\n"
                    )
                elif isinstance(msg, AIMessage):
                    conversation_context += (
                        f"Assistant: {msg.content[:200]}...\n"
                        if len(msg.content) > 200
                        else f"Assistant: {msg.content}\n"
                    )
            conversation_context += "\n"

        # Also include a summary of what's been created so far
        created_summary = ""
        if state["created_content"]:
            created_summary = "\nCONTENT CREATED SO FAR:\n"
            for item in state["created_content"]:
                created_summary += f"- {item['type']} (iteration {item['iteration']})\n"
            created_summary += "\n"

        intent = state.get("request_intent", "informational")
        created_types = [c["type"] for c in state.get("created_content", [])]
        has_answer = any("answer_lore_question" in ctype for ctype in created_types)
        search_done = bool(state.get("search_performed")) or bool(state.get("context_blocks"))

        if intent == "informational":
            important_notes = (
                "- The user is asking for lore information or clarification.\n"
                "- Use search_lore to gather canonical facts when needed.\n"
                "- Provide the answer with answer_lore_question or a concise summary referencing retrieved lore.\n"
                "- Avoid generating quests, NPCs, or other new content unless explicitly requested."
            )
            guidance = "- Build on the existing conversation if the user asked for more details."
            critical_decision = (
                f"1. Have you searched for lore? {'YES - found context' if search_done else 'NO - consider searching first'}\n"
                f"2. Have you provided a clear answer? {'YES - response prepared' if has_answer else 'NO - answer before finalizing'}"
            )
            incomplete_check = "Ensure the final answer directly addresses the user's request and references relevant lore."
        else:
            has_created = bool(created_types)
            important_notes = (
                "- The user wants you to CREATE content (stories, quests, NPCs, etc.)\n"
                "- After searching, you MUST call creation tools to generate the requested content\n"
                "- You can call the same tool multiple times if needed (e.g., two stories = call create_story_opening twice)\n"
                "- Only finalize AFTER you've created ALL the requested content\n"
                "- If unsure what to create, revisit the original request"
            )
            guidance = (
                "- If the request has multiple parts, create each component before finalizing."
            )
            critical_decision = (
                f"1. Have you searched for lore? {'YES - found context' if search_done else 'NO - search first'}\n"
                f"2. Have you created ALL requested content? {'YES - ready to finalize' if has_created else 'NO - MUST CREATE NOW'}"
            )
            incomplete_check = (
                f"Original request: {state['original_request']}\n"
                f"What you've created: {created_types}\n\n"
                "Ask yourself:\n"
                '- Does the request mention "quest" or "questline"? If yes, did you create one?\n'
                '- Does the request mention "stories"? If yes, did you create ALL of them?\n'
                "- Does the request mention combining or connecting things? If yes, did you create the connection?\n"
                "- If the request has multiple parts (stories AND quest), you MUST complete ALL parts before finalizing!"
            )

        # System prompt for reasoning
        reasoning_prompt = f"""Based on the current state, determine the NEXT SINGLE ACTION.

{conversation_context}{created_summary}Current Request: {state["original_request"]}
Iteration: {state["iteration_count"]}/{state["max_iterations"]}

PLAN OVERVIEW:
{plan_text}

RELEVANT LORE:
{lore_preview}

RECENT CREATIONS:
{recent_content}

IMPORTANT NOTES:
{important_notes}

{guidance}

SCRATCHPAD SUMMARY:
{reasoning_context}

Based on what's been done, what is the NEXT step?

CRITICAL DECISION POINT:
{critical_decision}

⚠️ INCOMPLETE TASK CHECK:
{incomplete_check}

NEVER finalize if any part of the request is incomplete!"""

        # Get LLM decision
        if intent == "informational":
            system_prompt = """You are a ReAct reasoning agent for the Luminari lore system. Your job is to:

1. Understand the user's lore question or clarification request
2. Search the archives when needed to gather canonical information
3. Provide the NEXT action that moves toward answering the question directly
4. Maintain consistency with prior assistant messages and the user's context
5. Finalize once you've delivered a clear, lore-grounded answer

CRITICAL:
- Prefer search_lore followed by answer_lore_question for informational queries
- Do NOT generate quests, NPCs, stories, or rewards unless the user explicitly asks for them
- Ensure every answer references retrieved lore or known canon

Response protocol:
- When you select a tool, return the tool call directly with arguments (function-call format). Do NOT describe the call in plain text.
- If everything requested is complete, respond with the exact word "finalize" and nothing else.
- Never emit free-form prose, bullet lists, or explanations otherwise – every turn must be either a tool call or "finalize"."""
        else:
            system_prompt = """You are a ReAct reasoning agent for the Luminari lore system. Your job is to:

1. Understand what the user is asking for - break down complex requests into logical steps
2. Review what's already been done (avoid unnecessary repetition)
3. Decide the NEXT action that best advances toward completing the request
4. Maintain consistency - use the same names, locations, and details throughout
5. When the task is complete, say action: "finalize"

CRITICAL: You MUST use tools to create the content the user requested. Don't finalize until you've created something!

Guidelines for flexible tool usage:
- You can call the same tool multiple times with different parameters when needed
- For "create two stories", call create_story_opening twice with different content
- For long or detailed narratives, call create_story (it returns a structured story with title, synopsis, sections, and characters)
- Use continue_story to expand an existing story section, passing any story metadata you already have
- For "create three NPCs", call create_npc three times
- Search for lore when you need canonical information
- Use create_complete_quest for comprehensive quest creation (it handles phases internally)
- Think step-by-step for complex, multi-part requests

Response protocol:
- When you select a tool, return the tool call directly with arguments (function-call format). Do NOT describe the call in plain text.
- If absolutely everything requested is complete, respond with the exact word "finalize" and nothing else.
- Never emit free-form prose, bullet lists, or explanations otherwise – every turn must be either a tool call or "finalize".

Examples of COMPLETE multi-step execution:

Example 1: "create two stories - one about elves, one about drow, then combine in a quest"
1. search_lore("elves pools of twilight")
2. search_lore("drow black bitch void's wake")
3. create_story_opening(protagonist="elves", setting="pools of twilight", conflict="protecting sacred waters")
4. create_story_opening(protagonist="drow hunters", setting="dark seas", conflict="hunting the Black Bitch pirate queen")
5. create_complete_quest(requirements="quest where player helps elves and unwittingly aids Black Bitch", lore_context=[from searches])
6. ONLY NOW: finalize

Example 2: "epic quest about a wizard"
1. search_lore("wizards magic arcane")
2. create_complete_quest(requirements="epic quest about wizard", lore_context=[search results])
3. finalize

CRITICAL: You MUST complete ALL content creation before finalizing!
- Searching alone is NOT enough
- Create ALL requested stories/quests/NPCs
- Use the exact tools shown in examples

⚠️ MULTI-PART REQUESTS: If the user asks for multiple things (e.g., "stories AND a quest"):
- You MUST create ALL parts before finalizing
- Creating only some parts is INCOMPLETE
- Example: "two stories and a quest" = create story 1, create story 2, create quest, THEN finalize
- NEVER finalize after creating just the stories if a quest was also requested!"""

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=reasoning_prompt)]

        # No tool_choice kwarg: "auto" is already the default once tools are bound, and
        # langchain-ollama forwards unknown kwargs straight to ollama.AsyncClient.chat(),
        # which has no tool_choice parameter and raises TypeError.
        response = await self.llm_with_tools.ainvoke(messages)

        # Add reasoning to scratchpad
        state["scratchpad"].append(
            {
                "step": "reason",
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "thought": response.content or "Determined next action",
                "tool_calls": (
                    [{"name": tc["name"], "args": tc["args"]} for tc in response.tool_calls]
                    if response.tool_calls
                    else []
                ),
            }
        )

        # Store planned action
        if response.tool_calls:
            state["current_step"] = {
                "tool_calls": response.tool_calls,
                "reasoning": response.content,
            }
        else:
            # Safety check: Don't finalize if we haven't completed the task
            created_entries = state.get("created_content", [])
            has_searched = bool(state.get("search_performed")) or bool(state.get("context_blocks"))
            has_answer = any("answer_lore_question" in entry["type"] for entry in created_entries)
            has_created = bool(created_entries)
            intent = state.get("request_intent", "informational")
            task_completed = has_answer if intent == "informational" else has_created

            # Trigger fallbacks when the model hesitates
            if not has_searched:
                fallback_search = self._build_search_fallback(state)
                if fallback_search:
                    logger.warning("No search performed yet; scheduling fallback search")
                    state["current_step"] = fallback_search
                    return state

            if has_searched and not task_completed:
                fallback_action = self._maybe_schedule_fallback_action(state)
                if fallback_action:
                    logger.warning(
                        "Search completed but no content generated; scheduling fallback content tool"
                    )
                    state["current_step"] = fallback_action
                    return state

            if has_searched and not task_completed and state["iteration_count"] < 10:
                logger.warning("Agent tried to finalize before completing required work")
                # Force the agent to reconsider by not finalizing
                reminder = (
                    "Need to provide an answer after searching"
                    if intent == "informational"
                    else "Need to create content after searching"
                )
                state["current_step"] = {"action": "reconsider", "reasoning": reminder}
            else:
                # OK to finalize
                state["current_step"] = {"action": "finalize", "reasoning": response.content}

        logger.info(
            f"Reasoning step {state['iteration_count']}: {len(response.tool_calls) if response.tool_calls else 0} tools planned"
        )

        return state

    async def _act_step(self, state: ReActState) -> dict[str, Any]:
        """Acting step: Execute the planned tools."""

        if not state["current_step"]:
            return state

        # Handle reconsider action (when agent tried to finalize too early)
        if state["current_step"].get("action") == "reconsider":
            logger.info("Agent reconsidering - needs to create content")
            return state

        # Execute tool calls if present
        if "tool_calls" not in state["current_step"]:
            return state

        tool_calls = state["current_step"]["tool_calls"]

        for tool_call in tool_calls:
            # Handle both dict and ToolCall object formats
            if hasattr(tool_call, "name"):
                # It's a ToolCall object
                tool_name = tool_call.name
                tool_args = tool_call.args
            else:
                # It's a dictionary
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

            if state.get("request_intent") == "informational":
                informational_allowed = {
                    "search_lore",
                    "answer_lore_question",
                    "get_entity_details",
                    "explore_relationships",
                    "verify_facts",
                    "validate_lore_consistency",
                }
                if tool_name not in informational_allowed:
                    logger.info(f"Skipping tool {tool_name} for informational request")
                    state["current_step"]["result"] = {
                        "error": f"Tool {tool_name} not appropriate for informational request"
                    }
                    continue

            # Check for loops
            tool_sig = (tool_name, json.dumps(tool_args, sort_keys=True))
            if tool_sig in state["tool_history"]:
                logger.warning(f"Skipping repeated tool call: {tool_name}")
                continue

            state["tool_history"].append(tool_sig)

            logger.info(f"Executing {tool_name}")

            try:
                # Execute tool
                tools_by_name = {t.name: t for t in self.tools}
                logger.info(f"Available tools: {list(tools_by_name.keys())}")

                if tool_name in tools_by_name:
                    tool = tools_by_name[tool_name]
                    logger.info(f"Tool {tool_name} type: {type(tool)}")
                    logger.info(
                        f"Tool {tool_name} attributes: {[attr for attr in dir(tool) if not attr.startswith('_')][:20]}"
                    )

                    # Enhance tool args with context for quest generation
                    enhanced_args = dict(tool_args)
                    lore_context = self._select_lore_context(state)

                    # For quest phase generation, add context about previous phases
                    if tool_name == "create_quest_phase":
                        # Get previous phases
                        quest_phases = [
                            c for c in state["created_content"] if "create_quest_phase" in c["type"]
                        ]
                        if quest_phases:
                            # Get the last phase's content
                            last_phase = quest_phases[-1]["content"]
                            if isinstance(last_phase, dict):
                                phase_summary = last_phase.get("phase_description", "")
                                enhanced_args["previous_phase"] = (
                                    phase_summary[:500] if phase_summary else None
                                )

                        # Add the original quest context
                        enhanced_args.setdefault("quest_context", state.get("original_request", ""))

                        # Add continuity instructions
                        quest_hook = next(
                            (
                                c
                                for c in state["created_content"]
                                if "create_quest_hook" in c["type"]
                            ),
                            None,
                        )
                        if quest_hook and isinstance(quest_hook["content"], dict):
                            hook_content = quest_hook["content"]
                            npcs = hook_content.get("important_npcs", [])
                            locations = hook_content.get("locations", [])
                            enhanced_args["maintain_continuity"] = (
                                f"NPCs: {', '.join(npcs[:3])}. Locations: {', '.join(locations[:3])}"
                            )
                        if lore_context and not enhanced_args.get("quest_context"):
                            enhanced_args["quest_context"] = "\n\n".join(lore_context)

                    # For combining phases, pass the actual phase content
                    elif tool_name == "combine_quest_phases":
                        quest_phases = [
                            c for c in state["created_content"] if "create_quest_phase" in c["type"]
                        ]
                        quest_hook = next(
                            (
                                c
                                for c in state["created_content"]
                                if "create_quest_hook" in c["type"]
                            ),
                            None,
                        )

                        # Create a summary of all phases
                        phase_summaries = []
                        for i, phase in enumerate(quest_phases, 1):
                            if isinstance(phase["content"], dict):
                                phase_summaries.append(
                                    f"Phase {i}: {phase['content'].get('phase_description', '')[:200]}"
                                )

                        enhanced_args["phase_summaries"] = "\n".join(phase_summaries)
                        enhanced_args["original_request"] = state.get("original_request", "")

                        if quest_hook and isinstance(quest_hook["content"], dict):
                            enhanced_args["quest_hook"] = quest_hook["content"].get("hook", "")
                        if lore_context:
                            enhanced_args.setdefault(
                                "original_request", state.get("original_request", "")
                            )
                            enhanced_args.setdefault("quest_hook", enhanced_args.get("quest_hook"))
                            enhanced_args.setdefault(
                                "phase_summaries", enhanced_args.get("phase_summaries")
                            )

                    # Inject lore context for creative tools when available
                    if tool_name == "answer_lore_question":
                        # The planner may paraphrase away user-visible constraints
                        # such as "one sentence". The original request is the
                        # authoritative question passed to the answer composer.
                        original_request = state.get("original_request", "")
                        if isinstance(original_request, str) and original_request.strip():
                            enhanced_args["question"] = original_request
                        # Retrieved state is already normalized to list[str].  Do not
                        # trust a model-supplied context shape over canonical state;
                        # StructuredTool correctly rejects strings/objects here.
                        enhanced_args["context"] = lore_context
                    elif lore_context:
                        if tool_name in {
                            "create_story",
                            "create_story_opening",
                            "continue_story",
                            "create_npc",
                            "create_location_description",
                            "create_dialogue",
                        }:
                            enhanced_args.setdefault("lore_context", lore_context)
                        elif tool_name == "create_complete_quest":
                            enhanced_args.setdefault("lore_context", lore_context)

                    # Tools created with @tool decorator have a specific structure
                    # They should be invoked with ainvoke() method
                    if hasattr(tool, "ainvoke"):
                        # This is a LangChain tool - use ainvoke
                        logger.info(f"Using tool.ainvoke for {tool_name}")
                        result = await tool.ainvoke(enhanced_args)
                    elif hasattr(tool, "__call__"):
                        # Direct callable
                        logger.info(f"Using direct call for {tool_name}")
                        result = await tool(**enhanced_args)
                    else:
                        raise ValueError(
                            f"Tool {tool_name} has no callable method (checked func, ainvoke, __call__)"
                        )

                    # Store result
                    state["current_step"]["result"] = result

                    # Special handling for certain tools
                    if tool_name == "search_lore":
                        # Mark retrieval as done even when it returns nothing, so the agent
                        # can move on and report the gap instead of re-searching forever.
                        state["search_performed"] = True
                        # Add to context blocks
                        if isinstance(result, dict):
                            if "context_blocks" in result:
                                state["context_blocks"].extend(result["context_blocks"])

                            # Log the rich data we found
                            if result.get("entities"):
                                logger.info(
                                    f"Found {len(result['entities'])} entities: {[e['name'] for e in result['entities'][:5]]}"
                                )
                            if result.get("relationships"):
                                logger.info(f"Found {len(result['relationships'])} relationships")

                    elif tool_name in [
                        "create_quest_phase",
                        "create_quest_hook",
                        "create_npc",
                        "create_story_opening",
                        "continue_story",
                        "answer_lore_question",
                        "create_quest_reward",
                        "create_location_description",
                        "create_dialogue",
                        "create_complete_quest",
                        "combine_quest_phases",
                    ]:
                        # Add to created content for quality tracking
                        state["created_content"].append(
                            {
                                "type": tool_name,
                                "content": result,
                                "iteration": state["iteration_count"],
                            }
                        )
                else:
                    raise ValueError(
                        f"Tool {tool_name} not found in tools. Available: {list(tools_by_name.keys())}"
                    )

            except Exception as e:
                logger.error("Tool execution failed (%s)", type(e).__name__)
                safe_error = public_error_message("Tool execution")
                state["current_step"]["result"] = {"error": safe_error}
                # Mark this tool as failed to prevent retry loops
                state["tool_history"].append((f"FAILED_{tool_name}", safe_error))

        return state

    async def _observe_step(self, state: ReActState) -> dict[str, Any]:
        """Observation step: Process results and update scratchpad."""

        if not state["current_step"] or "result" not in state["current_step"]:
            return state

        result = state["current_step"]["result"]

        # Create observation entry
        observation = {
            "step": "observe",
            "iteration": state["iteration_count"],
            "timestamp": datetime.now().isoformat(),
            "result_summary": self._summarize_result(result),
            "content_created": len(state["created_content"]),
        }

        # Add to scratchpad
        state["scratchpad"].append(observation)

        # Increment iteration
        state["iteration_count"] += 1

        logger.info("Tool observation recorded")

        return state

    async def _decide_step(self, state: ReActState) -> dict[str, Any]:
        """Decision step: Just passes through (routing happens in _should_continue)."""
        return state

    def _should_continue(self, state: ReActState) -> str:
        """Determine whether to continue reasoning or finalize."""

        # Check iteration limit
        if state["iteration_count"] >= state["max_iterations"]:
            logger.info("Reached max iterations, finalizing")
            return "finalize"

        # Check if last action was finalize
        if state["current_step"] and state["current_step"].get("action") == "finalize":
            return "finalize"

        # A successful grounded answer completes an informational request.  Do
        # not spend another provider call asking the model whether to finalize;
        # that adds latency and can discard an already-good answer if the extra
        # decision call encounters a transient transport failure.
        if state.get("request_intent") == "informational" and any(
            entry.get("type") == "answer_lore_question"
            for entry in state.get("created_content", [])
        ):
            logger.info("Grounded informational answer complete, finalizing")
            return "finalize"

        # Check for repeated errors (prevent infinite error loops)
        error_count = sum(1 for t in state["tool_history"] if t[0].startswith("FAILED_"))
        if error_count > 3:
            logger.warning(f"Too many tool failures ({error_count}), finalizing")
            return "finalize"

        # Check if we have enough content
        if "quest" in state["original_request"].lower():
            # For quests, check if we have phases
            quest_phases = [
                c for c in state["created_content"] if "create_quest_phase" in c["type"]
            ]
            if len(quest_phases) >= 3:  # Minimum 3 phases for a quest
                has_hook = any("create_quest_hook" in c["type"] for c in state["created_content"])
                has_combined = any(
                    "combine_quest_phases" in c["type"] for c in state["created_content"]
                )
                has_reward = any(
                    "create_quest_reward" in c["type"] for c in state["created_content"]
                )
                if has_hook and has_combined and has_reward:
                    logger.info("Quest complete with narrative arc, finalizing")
                    return "finalize"
                elif has_hook and not has_combined:
                    logger.info("Quest phases created but not combined yet")
                    return "continue"
                elif has_hook and has_combined and not has_reward:
                    logger.info("Quest narrative complete, needs rewards")
                    return "continue"

        # If plan complete and we have generated content, finalize
        plan = state.get("plan")
        if plan:
            plan_complete = all(item.get("status") == "done" for item in plan)
            if plan_complete and state.get("created_content"):
                logger.info("Plan finished with generated content; finalizing")
                return "finalize"

        # Continue reasoning
        return "continue"

    async def _finalize_step(self, state: ReActState) -> dict[str, Any]:
        """Finalize step: Compile and format the final result."""

        logger.info(f"Finalizing result with {len(state['created_content'])} content pieces")
        for content in state["created_content"]:
            logger.info(f"  - {content['type']}: {len(str(content['content']))} chars")

        # Compile final content
        final_result = {
            "original_request": state["original_request"],
            "iterations": state["iteration_count"],
            "content_pieces": len(state["created_content"]),
            "context_used": len(state["context_blocks"]),
            "content": state["created_content"],
            "scratchpad_size": len(state["scratchpad"]),
            "plan": state.get("plan", []),
        }

        # Add final message
        state["messages"].append(AIMessage(content=json.dumps(final_result)))

        return state

    def _build_reasoning_context(self, state: ReActState) -> str:
        """Build context from scratchpad for reasoning."""

        if not state["scratchpad"]:
            return "No previous actions taken yet. START with search_lore!"

        # Track what's been done
        tools_used = set()
        search_done = False
        hook_created = False
        story_started = False
        phases_created = 0

        for entry in state["scratchpad"]:
            if entry["step"] == "reason" and entry.get("tool_calls"):
                for tc in entry["tool_calls"]:
                    tool_name = tc["name"]
                    tools_used.add(tool_name)
                    if tool_name == "search_lore":
                        search_done = True
                    elif tool_name == "create_quest_hook":
                        hook_created = True
                    elif tool_name == "create_quest_phase":
                        phases_created += 1
                    elif tool_name == "create_story_opening":
                        story_started = True

        # Build clear summary
        parts = ["\n=== COMPLETED ACTIONS ==="]
        if search_done:
            parts.append("✓ Searched lore (DON'T repeat)")
        if hook_created:
            parts.append("✓ Created quest hook (DON'T create another)")
        if phases_created > 0:
            parts.append(f"✓ Created {phases_created} quest phases")
        if story_started:
            parts.append("✓ Created story opening (DON'T create another)")

        # Add warnings
        parts.append("\n=== WARNINGS ===")
        if phases_created >= 3:
            parts.append("⚠️ Already created enough quest phases - consider finalizing!")
        if len(tools_used) > 5:
            parts.append("⚠️ Many tools already used - task might be complete!")

        # Add content summary
        if state["created_content"]:
            parts.append("\n=== CONTENT CREATED ===")
            content_types = {}
            for c in state["created_content"]:
                content_types[c["type"]] = content_types.get(c["type"], 0) + 1

            for ctype, count in content_types.items():
                parts.append(f"  - {ctype}: {count}")

        return "\n".join(parts)

    async def _ensure_plan(self, state: ReActState) -> None:
        """Create a lightweight execution plan if one does not yet exist."""

        if state.get("plan"):
            return

        request = state.get("original_request", "")
        intent = state.get("request_intent", "informational")

        if intent == "informational":
            plan_steps = [
                {"step": "Search lore for supporting material", "status": "pending"},
                {"step": "Answer the user's question with the gathered lore", "status": "pending"},
                {"step": "Review answer and finalize", "status": "pending"},
            ]
            state["plan"] = plan_steps
            state["scratchpad"].append(
                {"step": "plan", "timestamp": datetime.now().isoformat(), "plan": plan_steps}
            )
            return

        context_snippets = self._select_lore_context(state, limit=2)
        context_text = (
            "\n".join(context_snippets) if context_snippets else "No supporting lore gathered yet."
        )

        messages = [
            SystemMessage(
                content="""You help a ReAct agent plan how to satisfy complex multi-step requests.
Outline 3-5 short actions in execution order. Reference the tools or outputs needed (search lore, create story, create quest, answer question, generate NPC, etc.).
Respond with a simple list, one action per line."""
            ),
            HumanMessage(content=f"User request: {request}\nKnown context:\n{context_text}"),
        ]

        try:
            response = await self.planner_llm.ainvoke(messages)
            raw_plan = response.content or ""
        except Exception as exc:  # pragma: no cover - planning failure fallback
            logger.warning("Planning step failed (%s)", type(exc).__name__)
            raw_plan = (
                "1. Search relevant lore\n2. Generate requested content\n3. Review and finalize"
            )

        plan_steps: list[dict[str, Any]] = []
        for line in raw_plan.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stripped = stripped.lstrip("-• ")
            if stripped and stripped[0].isdigit() and "." in stripped:
                stripped = stripped.split(".", 1)[1].strip()
            if stripped:
                plan_steps.append({"step": stripped, "status": "pending"})
            if len(plan_steps) >= 5:
                break

        if not plan_steps:
            plan_steps = [
                {"step": "Search lore for grounding", "status": "pending"},
                {"step": "Generate all requested content", "status": "pending"},
                {"step": "Review outputs and finalize", "status": "pending"},
            ]

        state["plan"] = plan_steps
        state["scratchpad"].append(
            {"step": "plan", "timestamp": datetime.now().isoformat(), "plan": plan_steps}
        )

    def _update_plan_progress(self, state: ReActState) -> None:
        """Mark plan steps as completed when matching work exists."""

        plan = state.get("plan")
        if not plan:
            return

        content_types = [c["type"] for c in state.get("created_content", [])]
        context_available = bool(state.get("context_blocks"))
        intent = state.get("request_intent", "informational")
        has_answer = any("answer_lore_question" in ct for ct in content_types)
        has_non_answer = any(ct != "answer_lore_question" for ct in content_types)

        for item in plan:
            step_text = item.get("step", "")
            lower = step_text.lower()
            status = item.get("status", "pending")

            if any(keyword in lower for keyword in ("search", "lore", "context")):
                status = "done" if context_available else "pending"
            elif "plan" in lower or "analyze" in lower or "break" in lower:
                status = "done"
            elif any(keyword in lower for keyword in ("story", "narrative", "tale")):
                status = "done" if any("story" in ct for ct in content_types) else status
            elif "quest" in lower:
                status = "done" if any("quest" in ct for ct in content_types) else status
            elif "npc" in lower or "character" in lower:
                status = "done" if any("create_npc" in ct for ct in content_types) else status
            elif "location" in lower or "place" in lower:
                status = (
                    "done"
                    if any("create_location_description" in ct for ct in content_types)
                    else status
                )
            elif "dialogue" in lower or "conversation" in lower:
                status = "done" if any("create_dialogue" in ct for ct in content_types) else status
            elif "reward" in lower:
                status = (
                    "done" if any("create_quest_reward" in ct for ct in content_types) else status
                )
            elif "answer" in lower and "question" in lower:
                status = "done" if has_answer else status
            elif "finalize" in lower or "review" in lower:
                if intent == "informational":
                    status = "done" if has_answer else status
                else:
                    status = "done" if has_non_answer else status

            item["status"] = status

    def _format_plan(self, state: ReActState) -> str:
        """Render the current plan for inclusion in prompts."""

        plan = state.get("plan")
        if not plan:
            return "Plan not established yet."

        lines = []
        for idx, step in enumerate(plan, 1):
            marker = "✅" if step.get("status") == "done" else "⬜"
            lines.append(f"{marker} Step {idx}: {step.get('step', '')}")
        return "\n".join(lines)

    def _format_context_preview(self, state: ReActState, limit: int = 3) -> str:
        """Provide a short preview of recently gathered lore."""

        contexts = self._select_lore_context(state, limit=limit)
        if not contexts:
            return "No lore retrieved yet."

        preview_lines = []
        for idx, ctx in enumerate(contexts[:limit], 1):
            snippet = ctx.strip()
            if len(snippet) > 260:
                snippet = f"{snippet[:260]}..."
            preview_lines.append(f"{idx}. {snippet}")
        return "\n".join(preview_lines)

    def _format_recent_content(self, state: ReActState, limit: int = 2) -> str:
        """Summarize the most recent generated content snippets."""

        created = state.get("created_content", [])
        if not created:
            return "No generated content yet."

        recent_entries = created[-limit:]
        lines = []
        for item in recent_entries:
            content_type = item.get("type", "content")
            content_preview = self._compact_content_preview(item.get("content"))
            lines.append(f"{content_type}: {content_preview}")
        return "\n".join(lines)

    def _select_lore_context(
        self, state: ReActState, limit: int = 10, char_limit: int = 4000
    ) -> list[str]:
        """Select recent lore context blocks, trimmed for prompt usage."""

        contexts: list[str] = []
        total_chars = 0
        for block in reversed(state.get("context_blocks", [])[-limit * 2 :]):
            text = self._extract_context_text(block)
            if not text:
                continue
            snippet = text.strip()
            if not snippet:
                continue
            if snippet in contexts:
                continue
            truncated = snippet[:400]
            contexts.append(truncated)
            total_chars += len(truncated)
            if len(contexts) >= limit or total_chars >= char_limit:
                break
        contexts.reverse()
        return contexts

    def _extract_context_text(self, block: Any) -> str:
        """Normalize context block payloads into plain text."""

        if isinstance(block, str):
            return block
        if isinstance(block, dict):
            for key in ("text", "content", "chunk", "summary", "body"):
                value = block.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return ""

    def _compact_content_preview(self, content: Any) -> str:
        """Generate a concise preview string for arbitrary content payloads."""

        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, dict):
            for key in (
                "hook_text",
                "phase_description",
                "description",
                "appearance",
                "answer",
                "content",
                "summary",
            ):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    text = value.strip()
                    break
            else:
                text = json.dumps(content)[:260]
        elif isinstance(content, list):
            joined = "; ".join(str(item) for item in content if isinstance(item, (str, dict)))
            text = joined.strip()
        else:
            text = str(content)

        if len(text) > 260:
            return f"{text[:260]}..."
        return text

    def _build_search_fallback(self, state: ReActState) -> dict[str, Any] | None:
        """Create a fallback search action when the agent skipped retrieval."""

        request = state.get("original_request", "").strip()
        if not request:
            return None

        query = request[:180]
        return {
            "tool_calls": [{"name": "search_lore", "args": {"query": query}}],
            "reasoning": "Fallback lore search using the user's original request",
        }

    def _maybe_schedule_fallback_action(self, state: ReActState) -> dict[str, Any] | None:
        """Choose an appropriate content tool when the model stalls."""

        request = state.get("original_request", "").strip()
        if not request:
            return None

        request_lower = request.lower()
        intent = state.get("request_intent", "informational")
        lore_context = self._select_lore_context(state)

        # Prefer full quest generation when explicitly requested
        quest_terms = ("quest", "questline", "adventure", "mission")
        if intent != "informational" and any(term in request_lower for term in quest_terms):
            args: dict[str, Any] = {"requirements": request}
            if lore_context:
                args["lore_context"] = lore_context
            return {
                "tool_calls": [{"name": "create_complete_quest", "args": args}],
                "reasoning": "Fallback quest generation using retrieved lore",
            }

        # Default to answering the question with available lore context
        answer_args: dict[str, Any] = {"question": request}
        if lore_context:
            answer_args["context"] = lore_context
        else:
            answer_args["context"] = []

        return {
            "tool_calls": [{"name": "answer_lore_question", "args": answer_args}],
            "reasoning": "Fallback lore answer due to missing generated content",
        }

    def _summarize_result(self, result: Any) -> str:
        """Summarize a tool result for the scratchpad."""

        if isinstance(result, dict):
            if "error" in result:
                return f"Error: {result['error']}"
            elif "context_blocks" in result:
                # Enhanced summary for search_lore results
                parts = [f"Found {len(result['context_blocks'])} context blocks"]
                if result.get("entities"):
                    parts.append(f"{len(result['entities'])} entities")
                if result.get("relationships"):
                    parts.append(f"{len(result['relationships'])} relationships")
                return ", ".join(parts)
            elif "phases" in result and "title" in result:
                # Complete quest result from create_complete_quest
                phase_count = len(result.get("phases", []))
                title = result.get("title", "Untitled Quest")
                has_resolution = "resolution" in result and result["resolution"]
                has_rewards = "rewards" in result and result["rewards"]
                parts = [f"Created complete quest '{title}' with {phase_count} phases"]
                if has_resolution:
                    parts.append("resolution")
                if has_rewards:
                    parts.append("rewards")
                return ", ".join(parts)
            elif "hook_text" in result:
                return "Created quest hook"
            elif "phase_description" in result:
                return "Created quest phase"
            elif "appearance" in result:
                return "Created NPC"
            else:
                keys = list(result.keys())[:3]
                return f"Created content with keys: {', '.join(keys)}"
        elif isinstance(result, str):
            return f"Generated text ({len(result)} chars)"
        else:
            return str(result)[:100]

    async def stream_chat(
        self,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        thread_id: str | None = None,
    ):
        """Stream the ReAct process with full transparency."""

        history = conversation_history or []
        intent = self._infer_request_intent(message, history)

        # Build message history
        messages = []
        if history:
            for msg in history[-10:]:  # Keep last 10 messages for context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    if role == "user":
                        messages.append(HumanMessage(content=content))
                    elif role == "assistant":
                        messages.append(AIMessage(content=content))

        # Add current message
        messages.append(HumanMessage(content=message))

        # Initialize state
        initial_state: ReActState = {
            "messages": messages,
            "scratchpad": [],
            "context_blocks": [],
            "search_performed": False,
            "created_content": [],
            "current_step": None,
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "original_request": message,
            "tool_history": [],
            "plan": None,
            "request_intent": intent,
            "story_cache": {},
        }

        # Load previous state if thread_id provided
        if thread_id:
            saved_state = await self.state_manager.get_state(thread_id)
            if saved_state:
                initial_state["scratchpad"] = saved_state.scratchpad
                initial_state["context_blocks"] = saved_state.context_blocks[-20:]  # Keep last 20
                logger.info(
                    f"Loaded state for thread {thread_id}: {len(saved_state.scratchpad)} scratchpad entries"
                )

        # Configure thread
        config = {"configurable": {"thread_id": thread_id or "default"}, "recursion_limit": 60}

        # Stream execution
        try:
            async for event in self.app.astream_events(initial_state, config, version="v1"):
                # Stream reasoning steps
                if event["event"] == "on_chain_start" and event["name"] == "reason":
                    yield {
                        "type": "reasoning",
                        "content": f"Step {initial_state['iteration_count'] + 1}: Analyzing situation...",
                    }

                # Stream action execution
                elif event["event"] == "on_chain_start" and event["name"] == "act":
                    if event.get("data"):
                        state_data = event["data"].get("input", {})
                        if state_data.get("current_step", {}).get("tool_calls"):
                            for tc in state_data["current_step"]["tool_calls"]:
                                yield {
                                    "type": "tool_use",
                                    "tool": tc["name"],
                                    "status": self._get_tool_description(tc["name"]),
                                }

                # Stream observations
                elif event["event"] == "on_chain_end" and event["name"] == "observe":
                    if event.get("data", {}).get("output"):
                        output = event["data"]["output"]
                        if output.get("scratchpad"):
                            last_obs = output["scratchpad"][-1]
                            if last_obs["step"] == "observe":
                                yield {
                                    "type": "observation",
                                    "content": last_obs.get("result_summary", "Processing..."),
                                }

                # Stream final result
                elif event["event"] == "on_chain_end" and event["name"] == "finalize":
                    if event.get("data", {}).get("output"):
                        final_state = event["data"]["output"]

                        logger.info(
                            f"Streaming final result with {len(final_state.get('created_content', []))} pieces"
                        )

                        # Format created content
                        formatted_content = self._format_final_content(
                            final_state.get("created_content", [])
                        )

                        logger.info(f"Formatted content length: {len(formatted_content)}")

                        yield {
                            "type": "final",
                            "content": formatted_content,
                            "metadata": {
                                "iterations": final_state.get("iteration_count", 0),
                                "content_pieces": len(final_state.get("created_content", [])),
                                "scratchpad_entries": len(final_state.get("scratchpad", [])),
                            },
                        }

                        # Save state if thread_id
                        if thread_id:
                            await self.state_manager.update_state(
                                thread_id=thread_id,
                                scratchpad_entry={
                                    "final": True,
                                    "timestamp": datetime.now().isoformat(),
                                },
                                context_blocks=final_state["context_blocks"][-10:],
                                generation={
                                    "content": final_state["created_content"],
                                    "plan": final_state.get("plan", []),
                                },
                            )

        except Exception as e:
            logger.error("ReAct streaming error (%s)", type(e).__name__)
            yield {"type": "error", "content": public_error_message("Chat stream")}

    def _get_tool_description(self, tool_name: str) -> str:
        """Get human-readable tool description."""
        descriptions = {
            "search_lore": "Searching lore archives...",
            "get_entity_details": "Retrieving entity details from knowledge graph...",
            "explore_relationships": "Exploring entity relationships...",
            "verify_facts": "Verifying facts against knowledge graph...",
            "answer_lore_question": "Formulating answer...",
            "create_quest_hook": "Creating quest introduction...",
            "create_quest_phase": "Designing quest phase...",
            "create_quest_reward": "Determining rewards...",
            "create_npc": "Creating character...",
            "create_location_description": "Describing location...",
            "create_story": "Crafting narrative blueprint...",
            "create_story_opening": "Beginning story...",
            "continue_story": "Continuing narrative...",
            "create_dialogue": "Writing dialogue...",
            "combine_quest_phases": "Assembling quest...",
            "validate_lore_consistency": "Checking consistency...",
            "create_complete_quest": "Creating complete quest with workflow...",
        }
        return descriptions.get(tool_name, f"Processing {tool_name}...")

    def _format_phase_markdown(self, phase: Any, index: int, heading_level: str = "###") -> str:
        """Turn structured quest phase data into readable markdown."""

        if phase is None:
            return ""

        def _make_heading(title: str) -> str:
            default_label = f"Phase {index}"
            label = title.strip() if title else default_label
            if not heading_level:
                return label
            if heading_level.startswith("#"):
                if label.lower().startswith(default_label.lower()):
                    return f"{heading_level} {label}"
                return f"{heading_level} {default_label}: {label}"
            if heading_level == "**":
                if label.lower().startswith(default_label.lower()):
                    return f"**{label}**"
                return f"**{default_label}: {label}**"
            if label.lower().startswith(default_label.lower()):
                return f"{heading_level} {label}"
            return f"{heading_level} {default_label}: {label}"

        if isinstance(phase, str):
            title = f"Phase {index}"
            heading = _make_heading(title)
            body = phase.strip()
            return f"{heading}\n\n{body}".strip()

        if not isinstance(phase, dict):
            return str(phase)

        title = (
            phase.get("phase_name") or phase.get("name") or phase.get("title") or f"Phase {index}"
        )
        heading = _make_heading(title)

        lines: list[str] = [heading]

        description = (
            phase.get("description") or phase.get("phase_description") or phase.get("summary")
        )
        if description:
            lines.extend(["", description.strip()])

        def _ensure_list(value: Any) -> list[str]:
            if not value:
                return []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            text = str(value).strip()
            return [text] if text else []

        objectives = _ensure_list(phase.get("objectives") or phase.get("tasks"))
        if objectives:
            lines.append("")
            lines.append("**Objectives:**")
            lines.extend([f"- {objective}" for objective in objectives])

        npcs = phase.get("npcs") or phase.get("allies")
        if npcs:
            lines.append("")
            lines.append("**NPCs:**")
            if isinstance(npcs, list) and npcs and isinstance(npcs[0], dict):
                for npc in npcs:
                    name = npc.get("name", "Unknown")
                    details = npc.get("role") or npc.get("description") or npc.get("notes")
                    if details:
                        lines.append(f"- {name}: {details}")
                    else:
                        lines.append(f"- {name}")
            else:
                for npc in _ensure_list(npcs):
                    lines.append(f"- {npc}")

        challenges = _ensure_list(phase.get("challenges") or phase.get("obstacles"))
        if challenges:
            lines.append("")
            lines.append("**Challenges:**")
            lines.extend([f"- {challenge}" for challenge in challenges])

        key_elements = _ensure_list(phase.get("key_elements") or phase.get("new_elements"))
        if key_elements:
            lines.append("")
            lines.append("**Key Elements:**")
            lines.extend([f"- {element}" for element in key_elements])

        final_challenge = phase.get("final_challenge")
        if final_challenge:
            lines.append("")
            lines.append("**Final Challenge:**")
            lines.extend([f"- {item}" for item in _ensure_list(final_challenge)])

        completion = phase.get("completion_trigger") or phase.get("completion")
        if completion:
            lines.append("")
            lines.append(f"**Completion:** {completion}")

        narrative_note = phase.get("narrative_note")
        if narrative_note:
            lines.append("")
            lines.append(f"**Narrative Note:** {narrative_note}")

        return "\n".join(lines).strip()

    def _format_rewards_markdown(
        self, rewards: Any, heading: str | None = "## Rewards"
    ) -> list[str]:
        """Turn reward payloads into readable Markdown bullets."""

        if not rewards:
            return []

        lines: list[str] = []

        if isinstance(rewards, str):
            if heading:
                lines.append(heading)
            lines.append(rewards.strip())
            return lines

        if isinstance(rewards, list):
            if heading:
                lines.append(heading)
            for item in rewards:
                if isinstance(item, dict):
                    name = item.get("name", "Reward")
                    desc = item.get("description")
                    lines.append(f"- **{name}:** {desc}" if desc else f"- **{name}**")
                else:
                    lines.append(f"- {item}")
            return lines

        if isinstance(rewards, dict):
            if heading:
                lines.append(heading)

            experience = rewards.get("experience")
            if experience is not None:
                if isinstance(experience, (int, float)):
                    lines.append(f"- **Experience:** {experience} XP")
                else:
                    lines.append(f"- **Experience:** {experience}")

            gold = rewards.get("gold")
            if gold is not None:
                if isinstance(gold, (int, float)):
                    lines.append(f"- **Gold:** {gold}")
                else:
                    lines.append(f"- **Gold:** {gold}")

            def _format_item(item: Any, label: str = "Item"):
                if not item:
                    return
                if isinstance(item, dict):
                    name = item.get("name", "Reward Item")
                    lines.append(f"- **{label}:** {name}")
                    description = item.get("description")
                    if description:
                        lines.append(f"  - Description: {description}")
                    properties = item.get("properties")
                    if properties:
                        if isinstance(properties, dict):
                            if properties:
                                lines.append("  - Properties:")
                                for prop_name, prop_value in properties.items():
                                    lines.append(f"    - {prop_name}: {prop_value}")
                        elif isinstance(properties, list):
                            if properties:
                                lines.append("  - Properties:")
                                for prop in properties:
                                    lines.append(f"    - {prop}")
                        else:
                            lines.append(f"  - Properties: {properties}")
                else:
                    lines.append(f"- **{label}:** {item}")

            _format_item(rewards.get("item_reward"))

            items = rewards.get("items")
            if items:
                for item in items:
                    _format_item(item)

            reputation = rewards.get("reputation")
            if reputation:
                if isinstance(reputation, dict):
                    lines.append("- **Reputation:**")
                    for faction, value in reputation.items():
                        lines.append(f"  - {faction}: {value}")
                else:
                    lines.append(f"- **Reputation:** {reputation}")

            special = rewards.get("special_reward") or rewards.get("special")
            if special:
                if isinstance(special, dict):
                    name = special.get("name")
                    description = special.get("description")
                    if name:
                        lines.append(f"- **Special:** {name}")
                        if description:
                            lines.append(f"  - {description}")
                    elif description:
                        lines.append(f"- **Special:** {description}")
                    else:
                        lines.append(f"- **Special:** {special}")
                elif isinstance(special, list):
                    lines.append("- **Special:**")
                    for entry in special:
                        lines.append(f"  - {entry}")
                else:
                    lines.append(f"- **Special:** {special}")

            return lines

        if heading:
            lines.append(heading)
        lines.append(str(rewards))
        return lines

    def _format_final_content(self, created_content: list[dict[str, Any]]) -> str:
        """Format the created content into a readable response."""

        if not created_content:
            return "I searched the lore but didn't generate a complete response. Please try again."

        # Group content by type
        by_type = {}
        for item in created_content:
            content_type = item["type"]
            if content_type not in by_type:
                by_type[content_type] = []
            # For answer_lore_question, append the full item to preserve metadata
            if content_type == "answer_lore_question":
                by_type[content_type].append(item)
            else:
                by_type[content_type].append(item["content"])

        # Format based on what was created
        parts = []

        if "create_story" in by_type:
            for item in by_type["create_story"]:
                story_payload = item if isinstance(item, dict) else {}
                if not story_payload:
                    parts.append(str(item))
                    continue

                title = story_payload.get("title", "Story")
                synopsis = story_payload.get("synopsis")
                tone = story_payload.get("tone")
                themes = story_payload.get("themes", [])
                characters = story_payload.get("characters", [])
                sections = story_payload.get("sections", [])
                lore_threads = story_payload.get("lore_threads", [])

                story_lines: list[str] = [f"## {title}\n"]

                if synopsis:
                    story_lines.append(f"**Synopsis:** {synopsis}\n")
                if tone or themes:
                    extra_meta = []
                    if tone:
                        extra_meta.append(f"Tone: {tone}")
                    if themes:
                        extra_meta.append("Themes: " + ", ".join(themes))
                    story_lines.append("**Overview:** " + " | ".join(extra_meta) + "\n")
                if characters:
                    story_lines.append("**Cast:**")
                    for char in characters:
                        name = char.get("name", "Unknown")
                        role = char.get("role", "")
                        motivation = char.get("motivation") or char.get("summary")
                        line = f"- {name}"
                        if role:
                            line += f" ({role})"
                        if motivation:
                            line += f": {motivation}"
                        story_lines.append(line)
                    story_lines.append("")
                if lore_threads:
                    story_lines.append("**Lore Threads:** " + ", ".join(lore_threads) + "\n")

                for idx, section in enumerate(sections, 1):
                    section_name = (
                        section.get("section_name") or section.get("name") or f"Section {idx}"
                    )
                    section_summary = section.get("summary")
                    section_text = section.get("text", "")
                    story_lines.append(f"### {section_name}")
                    if section_summary:
                        story_lines.append(f"_{section_summary}_")
                    story_lines.append("")
                    story_lines.append(section_text.strip())
                    story_lines.append("")

                if not sections and story_payload.get("full_story"):
                    story_lines.append(story_payload["full_story"].strip())

                parts.append("\n".join(story_lines).strip())

        # Answer to lore question
        if "answer_lore_question" in by_type:
            for item in by_type["answer_lore_question"]:
                # Extract the actual answer content
                if isinstance(item, dict) and "content" in item:
                    answer_content = item["content"]
                    if isinstance(answer_content, dict):
                        answer_text = answer_content.get("answer") or answer_content.get("content")
                        if answer_text:
                            parts.append(answer_text)
                        else:
                            parts.append(json.dumps(answer_content, indent=2))
                        coverage_lines: list[str] = []
                        used_blocks = answer_content.get(
                            "used_context_blocks"
                        ) or answer_content.get("used_blocks")
                        total_blocks = len(answer_content.get("context_blocks") or [])
                        if used_blocks:
                            note = f"- Context blocks consulted: {used_blocks}"
                            if total_blocks and used_blocks <= total_blocks:
                                note += f" of {total_blocks} retrieved"
                            coverage_lines.append(note)
                        digest = answer_content.get("context_digest") or {}
                        gaps = digest.get("gaps") if isinstance(digest, dict) else None
                        if gaps:
                            trimmed = []
                            for gap in gaps[:3]:
                                if isinstance(gap, dict):
                                    summary = gap.get("summary") or gap.get("detail")
                                else:
                                    summary = str(gap)
                                if summary:
                                    trimmed.append(summary)
                            if trimmed:
                                coverage_lines.append(
                                    "- Archive gaps acknowledged: " + "; ".join(trimmed)
                                )
                        retrieval_meta = answer_content.get("retrieval_metadata")
                        if isinstance(retrieval_meta, dict) and retrieval_meta:
                            metrics: list[str] = []
                            chunks = retrieval_meta.get("chunks_found")
                            if chunks is not None:
                                metrics.append(f"chunks {chunks}")
                            graph_entities = retrieval_meta.get("graph_entities")
                            if graph_entities is not None:
                                metrics.append(f"graph entities {graph_entities}")
                            graph_rels = retrieval_meta.get("graph_relationships")
                            if graph_rels is not None:
                                metrics.append(f"relationships {graph_rels}")
                            if metrics:
                                coverage_lines.append("- Retrieval metrics: " + ", ".join(metrics))
                        if coverage_lines:
                            parts.append("\n**Context Coverage:**\n" + "\n".join(coverage_lines))
                    else:
                        parts.append(str(answer_content))
                elif isinstance(item, str):
                    parts.append(item)
                else:
                    parts.append(str(item))

        # Complete quest from workflow
        if "create_complete_quest" in by_type:
            for quest in by_type["create_complete_quest"]:
                if isinstance(quest, dict):
                    # Format the complete quest beautifully
                    parts.append(f"# {quest.get('title', 'Epic Quest')}\n")

                    # Quest hook
                    if quest.get("hook"):
                        hook = quest["hook"]
                        if isinstance(hook, dict):
                            hook_text = (
                                hook.get("hook", "")
                                or hook.get("hook_text", "")
                                or hook.get("hook_description", "")
                            )
                            parts.append(f"## Quest Introduction\n\n{hook_text}\n")
                            if hook.get("initial_objective"):
                                parts.append(
                                    f"\n**Initial Objective:** {hook['initial_objective']}\n"
                                )
                        else:
                            parts.append(f"## Quest Introduction\n\n{hook}\n")

                    # Phases
                    if quest.get("phases"):
                        parts.append("")
                        parts.append("## Quest Phases")
                        for i, phase in enumerate(quest["phases"], 1):
                            formatted_phase = self._format_phase_markdown(
                                phase, i, heading_level="###"
                            )
                            if formatted_phase:
                                parts.append("")
                                parts.append(formatted_phase)

                    # Resolution
                    if quest.get("resolution"):
                        parts.append("\n## Resolution\n")
                        parts.append(f"{quest['resolution']}\n")

                    # Rewards
                    if quest.get("rewards"):
                        reward_lines = self._format_rewards_markdown(
                            quest["rewards"], heading="## Rewards"
                        )
                        if reward_lines:
                            if parts:
                                parts.append("")
                            parts.extend(reward_lines)

                    parts.append("\n---\n")

        # Quest content (individual components)
        if "create_quest_hook" in by_type:
            for hook in by_type["create_quest_hook"]:
                if isinstance(hook, dict):
                    parts.append(f"**Quest Hook:**\n{hook.get('hook_text', '')}\n")
                    parts.append(f"**Initial Objective:** {hook.get('initial_objective', '')}\n")
                elif isinstance(hook, str):
                    parts.append(f"**Quest Hook:**\n{hook}\n")

        if "create_quest_phase" in by_type:
            parts.append("")
            parts.append("## Quest Phases")
            for i, phase in enumerate(by_type["create_quest_phase"], 1):
                formatted_phase = self._format_phase_markdown(phase, i, heading_level="###")
                if formatted_phase:
                    parts.append("")
                    parts.append(formatted_phase)

        # Combined narrative summary
        if "combine_quest_phases" in by_type:
            parts.append("\n**Quest Narrative Arc:**\n")
            for narrative in by_type["combine_quest_phases"]:
                if isinstance(narrative, str):
                    parts.append(narrative)
                    parts.append("\n")

        if "create_quest_reward" in by_type:
            for reward in by_type["create_quest_reward"]:
                reward_lines = self._format_rewards_markdown(reward, heading="## Rewards")
                if reward_lines:
                    if parts:
                        parts.append("")
                    parts.extend(reward_lines)

        # Story content
        if "create_story_opening" in by_type:
            for opening in by_type["create_story_opening"]:
                if isinstance(opening, str):
                    parts.append(f"{opening}\n")
                else:
                    parts.append(f"**Story:**\n\n{opening}\n")

        if "continue_story" in by_type:
            for continuation in by_type["continue_story"]:
                parts.append(f"\n{continuation}\n")

        # NPC content
        if "create_npc" in by_type:
            for npc in by_type["create_npc"]:
                if isinstance(npc, dict):
                    parts.append("\n**NPC:**\n")
                    parts.append(f"*Appearance:* {npc.get('appearance', '')}\n")
                    parts.append(f"*Backstory:* {npc.get('backstory', '')}\n")
                    parts.append(f"*Dialogue Style:* {npc.get('dialogue_style', '')}\n")
                elif isinstance(npc, str):
                    parts.append(f"\n**NPC:**\n{npc}\n")

        # Location descriptions
        if "create_location_description" in by_type:
            for desc in by_type["create_location_description"]:
                parts.append(f"\n**Location:**\n{desc}\n")

        # Dialogue
        if "create_dialogue" in by_type:
            for dialogue in by_type["create_dialogue"]:
                parts.append(f"\n**Dialogue:**\n{dialogue}\n")

        # If no specific formatting matched but we have content, show it
        if not parts and by_type:
            for content_type, contents in by_type.items():
                for content in contents:
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, dict):
                        # Format dict nicely
                        for key, value in content.items():
                            if key != "error":
                                parts.append(f"**{key.replace('_', ' ').title()}:** {value}")

        return "\n".join(parts) if parts else "Content was created but formatting failed."

    async def chat(
        self,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat for compatibility."""

        full_response = ""
        metadata = {}

        async for event in self.stream_chat(message, conversation_history, thread_id):
            if event["type"] == "final":
                full_response = event["content"]
                metadata = event.get("metadata", {})

        return {"answer": full_response, "metadata": metadata, "engine": "react"}
