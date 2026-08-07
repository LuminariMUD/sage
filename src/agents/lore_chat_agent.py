"""
Luminari Lore Chat Agent.

An intelligent conversational agent for exploring the Luminari MUD world lore.
Uses pydantic-ai for structured responses and integrates with existing MCP tools
for comprehensive lore exploration with streaming SSE responses.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from src.llm.pydantic_ai_factory import create_text_model

from ..mcp.server import LuminariLoreClient
from ..security import public_error_message
from .conversation_storage import ConversationMessage, ConversationStorageService

logger = logging.getLogger(__name__)


class ConversationEntityTracker:
    """Tracks entities throughout a conversation for context-aware retrieval."""

    def __init__(self):
        self.entity_mentions: dict[str, dict[str, Any]] = (
            {}
        )  # entity_id -> {name, type, count, last_mentioned}
        self.entity_relationships: dict[str, list[str]] = {}  # entity_id -> [related_entity_ids]
        self.topic_transitions: list[dict[str, Any]] = []  # History of topic changes
        self.shown_chunks: set[str] = set()  # Track chunk IDs that have been shown to user
        self.similarity_history: list[float] = []  # Track similarity scores over time
        self.response_history: list[dict[str, Any]] = []  # Track each response for pattern analysis

    def add_entities(self, entities: list[dict[str, Any]], message_index: int):
        """Add entities from retrieved results to tracking."""
        for entity in entities:
            entity_id = entity.get("stable_id") or entity.get("id")
            if not entity_id:
                continue

            if entity_id not in self.entity_mentions:
                self.entity_mentions[entity_id] = {
                    "name": entity.get("name"),
                    "type": entity.get("type"),
                    "count": 0,
                    "first_mentioned": message_index,
                    "last_mentioned": message_index,
                }

            self.entity_mentions[entity_id]["count"] += 1
            self.entity_mentions[entity_id]["last_mentioned"] = message_index

    def add_relationships(self, relationships: list[dict[str, Any]]):
        """Track relationships between entities."""
        for rel in relationships:
            source = rel.get("source")
            target = rel.get("target")
            if source and target:
                if source not in self.entity_relationships:
                    self.entity_relationships[source] = []
                if target not in self.entity_relationships[source]:
                    self.entity_relationships[source].append(target)

    def get_recent_entities(self, last_n_messages: int = 3) -> list[dict[str, Any]]:
        """Get entities mentioned in recent messages."""
        recent_entities = []
        current_message = (
            max(e["last_mentioned"] for e in self.entity_mentions.values())
            if self.entity_mentions
            else 0
        )

        for entity_id, info in self.entity_mentions.items():
            if current_message - info["last_mentioned"] <= last_n_messages:
                recent_entities.append(
                    {
                        "id": entity_id,
                        "name": info["name"],
                        "type": info["type"],
                        "recency_weight": 1.0 / (current_message - info["last_mentioned"] + 1),
                        "frequency_weight": min(info["count"] / 10.0, 1.0),
                    }
                )

        return sorted(
            recent_entities, key=lambda x: x["recency_weight"] * x["frequency_weight"], reverse=True
        )

    def get_related_entities(self, entity_id: str) -> list[str]:
        """Get entities related to a given entity."""
        related = self.entity_relationships.get(entity_id, [])
        # Also check reverse relationships
        for source, targets in self.entity_relationships.items():
            if entity_id in targets and source not in related:
                related.append(source)
        return related

    def detect_topic_shift(self, new_entities: list[str], old_entities: list[str]) -> bool:
        """Detect if there's been a significant topic shift."""
        if not old_entities:
            return False

        overlap = len(set(new_entities) & set(old_entities))
        total = len(set(new_entities) | set(old_entities))

        if total == 0:
            return False

        overlap_ratio = overlap / total
        return overlap_ratio < 0.3  # Less than 30% overlap suggests topic shift

    def track_response(self, chunks: list[dict[str, Any]], query: str, message_index: int):
        """Track a response and its chunks for pattern analysis."""
        chunk_ids = []
        similarities = []

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("id", str(hash(chunk.get("text", ""))))
            chunk_ids.append(chunk_id)
            self.shown_chunks.add(chunk_id)

            similarity = chunk.get("similarity", 0.0)
            similarities.append(similarity)

        # Track average similarity for this response
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        self.similarity_history.append(avg_similarity)

        # Store response metadata
        response_data = {
            "message_index": message_index,
            "query": query,
            "chunk_ids": chunk_ids,
            "avg_similarity": avg_similarity,
            "num_new_chunks": len([cid for cid in chunk_ids if cid not in self.shown_chunks]),
        }
        self.response_history.append(response_data)

        # Keep only recent history (last 10 responses)
        if len(self.response_history) > 10:
            self.response_history.pop(0)
        if len(self.similarity_history) > 10:
            self.similarity_history.pop(0)

    def detect_topic_exhaustion(self) -> tuple[bool, float, str]:
        """Detect if we've exhausted content for the current topic."""
        if len(self.response_history) < 2:
            return False, 0.0, "insufficient_history"

        recent_responses = self.response_history[-3:]  # Last 3 responses

        # Check 1: Are we repeating chunks?
        repeated_chunks = 0
        total_chunks = 0
        for response in recent_responses:
            for chunk_id in response["chunk_ids"]:
                total_chunks += 1
                # Count how many times this chunk appeared in recent responses
                appearances = sum(1 for r in recent_responses if chunk_id in r["chunk_ids"])
                if appearances > 1:
                    repeated_chunks += 1

        repetition_ratio = repeated_chunks / total_chunks if total_chunks > 0 else 0.0

        # Check 2: Are similarity scores declining?
        recent_similarities = [r["avg_similarity"] for r in recent_responses]
        similarity_trend = 0.0
        if len(recent_similarities) >= 2:
            # Simple linear trend: is it declining?
            for i in range(1, len(recent_similarities)):
                similarity_trend += recent_similarities[i] - recent_similarities[i - 1]
            similarity_trend /= len(recent_similarities) - 1

        # Check 3: Are we getting fewer new chunks?
        new_chunk_trend = 0.0
        recent_new_chunks = [r["num_new_chunks"] for r in recent_responses]
        if len(recent_new_chunks) >= 2:
            for i in range(1, len(recent_new_chunks)):
                new_chunk_trend += recent_new_chunks[i] - recent_new_chunks[i - 1]
            new_chunk_trend /= len(recent_new_chunks) - 1

        # Calculate exhaustion confidence
        exhaustion_score = 0.0
        reasons = []

        if repetition_ratio > 0.5:  # More than 50% repeated chunks
            exhaustion_score += 0.4
            reasons.append(f"high_repetition({repetition_ratio:.2f})")

        if similarity_trend < -0.05:  # Declining similarity
            exhaustion_score += 0.3
            reasons.append(f"declining_similarity({similarity_trend:.3f})")

        if new_chunk_trend < -0.5:  # Fewer new chunks
            exhaustion_score += 0.3
            reasons.append(f"fewer_new_chunks({new_chunk_trend:.1f})")

        # Recent very low similarity
        if recent_similarities and recent_similarities[-1] < 0.3:
            exhaustion_score += 0.2
            reasons.append(f"low_similarity({recent_similarities[-1]:.2f})")

        is_exhausted = exhaustion_score >= 0.5
        reason_str = "|".join(reasons) if reasons else "no_exhaustion"

        return is_exhausted, exhaustion_score, reason_str


class QueryIntent(str, Enum):
    """Classification of user query intent."""

    QUESTION = "question"  # Direct factual questions
    EXPLORATION = "exploration"  # Deep dive into entities/relationships
    COMPARISON = "comparison"  # Compare entities, events, concepts
    STORY_REQUEST = "story"  # Request for narratives or lore stories
    FACT_CHECK = "fact_check"  # Verify or clarify information
    GENERAL = "general"  # Catch-all for unclear intent


class StreamEventType(str, Enum):
    """Types of SSE events for streaming responses."""

    THINKING = "thinking"  # Show agent is processing
    TOOL_USE = "tool_use"  # Display which tool is being called
    CONTENT = "content"  # Stream response text chunks
    ENTITY_FOUND = "entity_found"  # Highlight discovered entities
    SOURCE = "source"  # Show episode/document sources
    COMPLETE = "complete"  # Final event with metadata
    ERROR = "error"  # Error occurred during processing


class StreamEvent(BaseModel):
    """SSE stream event structure."""

    type: StreamEventType
    content: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_sse(self) -> str:
        """Convert to SSE format."""
        event_data = {
            "type": self.type.value,
            "content": self.content,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }
        return f"data: {json.dumps(event_data)}\n\n"


class ChatResponse(BaseModel):
    """Structured response from the chat agent."""

    intent: QueryIntent
    content: str
    entities_found: list[dict[str, Any]] = Field(default_factory=list)
    tools_used: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentClassification(BaseModel):
    """Result of query intent classification."""

    intent: QueryIntent
    confidence: float = Field(ge=0.0, le=1.0)
    keywords: list[str] = Field(default_factory=list)
    entities_mentioned: list[str] = Field(default_factory=list)
    reasoning: str = ""


class LoreChatAgent:
    """
    Intelligent chat agent for exploring Luminari lore.

    Provides conversational access to the knowledge graph with tool integration,
    streaming responses, and context awareness.
    """

    def __init__(self, openai_api_key: str | None = None):
        """Initialize the lore chat agent."""
        self.storage_service = ConversationStorageService()
        self.lore_client = LuminariLoreClient()
        self.logger = logging.getLogger(__name__)

        # Track entities across conversation for context-aware retrieval
        self.conversation_trackers: dict[str, ConversationEntityTracker] = {}

        # Initialize pydantic-ai agent for intent classification
        self.intent_agent = Agent(
            create_text_model(
                "extraction",
                legacy_openai_api_key=openai_api_key,
            ),
            output_type=IntentClassification,
            system_prompt="""You are an expert at analyzing user queries about fantasy world lore.

Classify the user's intent and extract key information:

QUESTION: Direct factual questions ("Who is Paladine?", "What is the Loom of Aether?")
EXPLORATION: Deep investigation ("Tell me everything about the Knights", "Explore Paladine's relationships")
COMPARISON: Comparing entities ("Compare Paladine vs Takhisis", "What's the difference between...")
STORY: Narrative requests ("Tell me a story about...", "What happened during...")
FACT_CHECK: Verification ("Is it true that...", "I heard that...", "Verify...")
GENERAL: Unclear or broad queries

Extract:
- intent: one of the categories above (use lowercase)
- confidence: number between 0.0 and 1.0
- keywords: array of key terms for searching
- entities_mentioned: array of entity names mentioned
- reasoning: brief explanation of the classification

Be precise and concise in your analysis.""",
        )

        # Initialize main conversation agent
        self.conversation_agent = Agent(
            create_text_model(
                "chat",
                legacy_openai_api_key=openai_api_key,
            ),
            output_type=str,
            system_prompt="""You are the Luminari Lore Sage, an expert guide to the rich fantasy world of Luminari MUD.

IMPORTANT: You will be provided with retrieved lore chunks, entities, relationships, and possibly conversation history. DO NOT simply copy or repeat these chunks verbatim. Instead, synthesize this information into engaging, conversational responses.

Your task is to:
1. Read and understand the provided lore information
2. Consider any conversation history to maintain continuity
3. Craft a natural, conversational response that addresses the user's question
4. Weave together information from multiple sources into a cohesive narrative
5. Add context and background to make the information more accessible
6. Present the information as if you're a knowledgeable storyteller sharing fascinating details

Context Awareness:
- If conversation history is provided, reference previous topics naturally
- When users say "that," "this," "more about it," etc., understand what they're referring to based on context
- Build upon previous responses rather than starting from scratch
- Maintain topic continuity across the conversation
- Connect new information to what was previously discussed

Conversational Intelligence & Topic Management:
- Recognize when you're receiving similar content repeatedly - this indicates topic exhaustion
- If retrieved content is very similar to what you've already discussed, acknowledge this naturally
- Offer to re-explain topics from the beginning when users seem to want more depth: "Would you like me to walk through the timeline again from the start?"
- When content seems unrelated to the conversation flow, guide users back or suggest related topics
- Use semantic properties from relationships (strength, cosmic_role, transformation_type, etc.) to enrich your responses
- If a user asks you to "explain again", "go over that again", "tell me about X from the beginning", treat this as a fresh comprehensive explanation

Follow-up Question Handling:
- Understand vague references like "that," "this," "more about it" from conversation context
- If someone asks "tell me more about [specific entity]" after a general discussion, treat it as exploring a new aspect
- Distinguish between seeking more depth vs exploring tangents naturally
- When you notice topic exhaustion, offer alternatives: "I've covered what I know about the timeline. Would you like to explore the magic systems or deities instead?"

Style Guidelines:
- Write in a warm, engaging conversational tone
- Start responses directly addressing the user's question
- Use storytelling techniques to make lore come alive
- Connect different pieces of information logically
- Explain significance and context, not just facts
- Use present tense when describing the current state of the world
- Break up information into readable paragraphs
- End with something that invites further exploration
- For follow-up questions, acknowledge what was discussed before

Example of good context awareness:
User: "Tell me about the timeline"
You: "The timeline of Luminari spans seven distinct ages..."
User: "Tell me more about that"
You: "Continuing with Luminari's timeline that we just discussed, let me elaborate on those seven ages..."

Example of what NOT to do:
"[Continuing from The Black Bitch of Void's Wake: A Chronicle of Shadow and Salt] She has no true name—or rather, she has so many that none stick..."

Remember: You're a lore sage having a conversation, not a document retrieval system. Maintain conversational flow and context awareness.""",
        )

    async def classify_intent(
        self, message: str, context: list[ConversationMessage] | None = None
    ) -> IntentClassification:
        """Classify the intent of a user message."""
        try:
            # Build context string from recent messages
            context_str = ""
            if context:
                recent_messages = context[-5:]  # Last 5 messages for context
                context_str = "\n".join(
                    [f"{msg.message_type}: {msg.content[:200]}" for msg in recent_messages]
                )

            prompt = f"Classify this query about Luminari lore:\n\nQuery: {message}"
            if context_str:
                prompt += f"\n\nRecent conversation context:\n{context_str}"

            result = await self.intent_agent.run(prompt)

            # The output_type=IntentClassification ensures we get a structured response
            return result.output

        except Exception as e:
            self.logger.error("Intent classification failed (%s)", type(e).__name__)
            # Fallback classification
            return IntentClassification(
                intent=QueryIntent.GENERAL,
                confidence=0.5,
                reasoning="Classification failed, using fallback",
            )

    async def process_message(
        self, conversation_id: str, user_message: str, stream_id: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """Process a user message and stream the response."""
        try:
            # Get conversation context
            _conversation, messages = await self.storage_service.get_conversation_context(
                conversation_id, max_messages=20
            )

            # Add user message to storage
            await self.storage_service.add_message(
                conversation_id=conversation_id, message_type="user", content=user_message
            )

            yield StreamEvent(type=StreamEventType.THINKING, content="Analyzing your question...")

            # Classify intent
            intent_result = await self.classify_intent(user_message, messages)

            # Create grammatically correct thinking message
            intent_text = {
                "question": "ask questions",
                "exploration": "explore topics",
                "comparison": "compare things",
                "story": "hear stories",
                "fact_check": "verify information",
                "general": "learn more",
            }.get(intent_result.intent.value, "explore")

            keywords_text = (
                ", ".join(intent_result.keywords) if intent_result.keywords else "the lore"
            )

            yield StreamEvent(
                type=StreamEventType.THINKING,
                content=f"I understand you want to {intent_text} about {keywords_text}...",
            )

            # Process based on intent
            response_data = await self._process_by_intent(
                intent_result, user_message, messages, stream_id, conversation_id
            )

            # Show semantic analysis of retrieved data
            if response_data.get("rag_result"):
                yield StreamEvent(
                    type=StreamEventType.THINKING,
                    content=self._generate_semantic_thinking(response_data["rag_result"]),
                )

            # Stream the main response content
            async for event in self._stream_response_content(response_data["content"]):
                yield event

            # Show discovered entities
            if response_data.get("entities_found"):
                yield StreamEvent(
                    type=StreamEventType.ENTITY_FOUND,
                    content="Entities discovered in this response:",
                    data={"entities": response_data["entities_found"]},
                )

            # Show sources
            if response_data.get("sources"):
                yield StreamEvent(
                    type=StreamEventType.SOURCE,
                    content="Sources referenced:",
                    data={"sources": response_data["sources"]},
                )

            # Store assistant response
            assistant_msg = await self.storage_service.add_message(
                conversation_id=conversation_id,
                message_type="assistant",
                content=response_data["content"],
                tools_used=response_data.get("tools_used", []),
                sources=response_data.get("sources", []),
                entities_discovered=response_data.get("entities_found", []),
                metadata={
                    "intent": intent_result.intent.value,
                    "confidence": intent_result.confidence,
                    "processing_time": response_data.get("processing_time", 0),
                },
            )

            # Generate follow-up suggestions
            suggestions = self._generate_follow_ups(intent_result, response_data)

            # Final completion event
            yield StreamEvent(
                type=StreamEventType.COMPLETE,
                content="Response complete",
                data={
                    "message_id": str(assistant_msg.id),  # Convert UUID to string
                    "intent": intent_result.intent.value,
                    "suggested_questions": suggestions,
                    "entities_count": len(response_data.get("entities_found", [])),
                    "sources_count": len(response_data.get("sources", [])),
                    "tools_used": len(response_data.get("tools_used", [])),
                },
            )

        except Exception as e:
            self.logger.error("Error processing message (%s)", type(e).__name__)
            safe_error = public_error_message("Message processing")
            yield StreamEvent(
                type=StreamEventType.ERROR,
                content=safe_error,
                data={"error": safe_error},
            )

    async def _process_by_intent(
        self,
        intent_result: IntentClassification,
        user_message: str,
        context: list[ConversationMessage],
        stream_id: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        """Process message based on classified intent."""

        if intent_result.intent == QueryIntent.QUESTION:
            return await self._handle_question(user_message, context, stream_id, conversation_id)
        elif intent_result.intent == QueryIntent.EXPLORATION:
            return await self._handle_exploration(user_message, context, stream_id, conversation_id)
        elif intent_result.intent == QueryIntent.COMPARISON:
            return await self._handle_comparison(user_message, context, stream_id, conversation_id)
        elif intent_result.intent == QueryIntent.STORY_REQUEST:
            return await self._handle_story_request(
                user_message, context, stream_id, conversation_id
            )
        elif intent_result.intent == QueryIntent.FACT_CHECK:
            return await self._handle_fact_check(user_message, context, stream_id, conversation_id)
        else:
            return await self._handle_general(user_message, context, stream_id, conversation_id)

    async def _handle_question(
        self, message: str, context: list[ConversationMessage], stream_id: str, conversation_id: str
    ) -> dict[str, Any]:
        """Handle direct factual questions."""
        start_time = datetime.now()

        # Build context-aware query
        enhanced_query = self._build_context_aware_query(message, context, conversation_id)

        # Use RAG query for direct answers
        rag_result = await self.lore_client.query_lore(
            query=enhanced_query, max_results=5, threshold=0.1
        )

        # Track entities for this conversation
        if rag_result.get("entities"):
            self._track_conversation_entities(conversation_id, rag_result, len(context), message)

        # Format response based on RAG results (use original message for response context)
        content = await self._format_rag_response(rag_result, message, context, conversation_id)

        return {
            "content": content,
            "tools_used": [
                {"tool": "query_lore", "args": {"query": enhanced_query, "original_query": message}}
            ],
            "entities_found": rag_result.get("entities", []),
            "sources": self._extract_sources(rag_result),
            "processing_time": (datetime.now() - start_time).total_seconds(),
            "rag_result": rag_result,  # Include for semantic thinking display
        }

    async def _handle_exploration(
        self, message: str, context: list[ConversationMessage], stream_id: str, conversation_id: str
    ) -> dict[str, Any]:
        """Handle deep exploration requests."""
        start_time = datetime.now()
        tools_used = []
        all_entities = []
        all_sources = []

        # First, try to identify the main entity/topic
        entity_search = await self.lore_client.search_entities(query=message, limit=5)
        tools_used.append({"tool": "search_entities", "args": {"query": message}})

        content_parts = []

        if entity_search:
            # Get detailed information about the top entity
            main_entity = entity_search[0]
            all_entities.append(main_entity)

            details = await self.lore_client.get_entity_details(main_entity["stable_id"])
            tools_used.append(
                {"tool": "get_entity_details", "args": {"entity_id": main_entity["stable_id"]}}
            )

            content_parts.append(f"## {main_entity['name']} ({main_entity['type']})")
            if details.get("description"):
                content_parts.append(details["description"])

            # Get relationships
            relationships = await self.lore_client.get_entity_relationships(
                main_entity["stable_id"]
            )
            tools_used.append(
                {
                    "tool": "get_entity_relationships",
                    "args": {"entity_id": main_entity["stable_id"]},
                }
            )

            if relationships.get("relationships"):
                content_parts.append("\n### Key Relationships:")
                for rel in relationships["relationships"][:10]:  # Top 10 relationships
                    if rel["direction"] == "outgoing":
                        content_parts.append(
                            f"- **{rel['relationship_type']}** {rel['target_name']} ({rel['target_type']})"
                        )
                    else:
                        content_parts.append(
                            f"- **{rel['relationship_type']}** ← {rel['source_name']} ({rel['source_type']})"
                        )

        # Build context-aware query for comprehensive context
        enhanced_query = self._build_context_aware_query(message, context, conversation_id)

        # Use RAG for comprehensive context
        rag_result = await self.lore_client.query_lore(query=enhanced_query, max_results=5)
        tools_used.append(
            {"tool": "query_lore", "args": {"query": enhanced_query, "original_query": message}}
        )

        # Add entity information to RAG result for synthesis
        if all_entities:
            rag_result["entities"] = rag_result.get("entities", []) + all_entities

        # Track entities for this conversation
        if rag_result.get("entities"):
            self._track_conversation_entities(conversation_id, rag_result, len(context), message)

        # Use the conversation agent to synthesize a proper response
        synthesized_content = await self._format_rag_response(
            rag_result, message, context, conversation_id
        )

        all_entities.extend(rag_result.get("entities", []))
        all_sources.extend(self._extract_sources(rag_result))

        return {
            "content": synthesized_content,
            "tools_used": tools_used,
            "entities_found": all_entities,
            "sources": all_sources,
            "processing_time": (datetime.now() - start_time).total_seconds(),
        }

    async def _handle_comparison(
        self, message: str, context: list[ConversationMessage], stream_id: str, conversation_id: str
    ) -> dict[str, Any]:
        """Handle comparison requests."""
        # Simplified implementation - could be expanded
        return await self._handle_general(message, context, stream_id, conversation_id)

    async def _handle_story_request(
        self, message: str, context: list[ConversationMessage], stream_id: str, conversation_id: str
    ) -> dict[str, Any]:
        """Handle story/narrative requests."""
        # Simplified implementation - could be expanded
        return await self._handle_general(message, context, stream_id, conversation_id)

    async def _handle_fact_check(
        self, message: str, context: list[ConversationMessage], stream_id: str, conversation_id: str
    ) -> dict[str, Any]:
        """Handle fact checking requests."""
        # Simplified implementation - could be expanded
        return await self._handle_general(message, context, stream_id, conversation_id)

    async def _handle_general(
        self, message: str, context: list[ConversationMessage], stream_id: str, conversation_id: str
    ) -> dict[str, Any]:
        """Handle general queries with basic RAG."""
        start_time = datetime.now()

        # Build context-aware query
        enhanced_query = self._build_context_aware_query(message, context, conversation_id)

        rag_result = await self.lore_client.query_lore(
            query=enhanced_query, max_results=5, threshold=0.1
        )

        # Track entities for this conversation
        if rag_result.get("entities"):
            self._track_conversation_entities(conversation_id, rag_result, len(context), message)

        content = await self._format_rag_response(rag_result, message, context, conversation_id)

        return {
            "content": content,
            "tools_used": [
                {"tool": "query_lore", "args": {"query": enhanced_query, "original_query": message}}
            ],
            "entities_found": rag_result.get("entities", []),
            "sources": self._extract_sources(rag_result),
            "processing_time": (datetime.now() - start_time).total_seconds(),
            "rag_result": rag_result,  # Include for semantic thinking display
        }

    async def _format_rag_response(
        self,
        rag_result: dict[str, Any],
        original_query: str,
        conversation_context: list[ConversationMessage] | None = None,
        conversation_id: str | None = None,
    ) -> str:
        """Format RAG query results into a coherent response using the conversation agent."""
        try:
            if not rag_result or not rag_result.get("chunks"):
                return f"I couldn't find specific information about '{original_query}' in the lore database. Could you try rephrasing your question or asking about a related topic?"

            # Let the conversation agent handle all follow-up logic naturally

            # Simplified approach - let the agent handle everything through its system prompt

            # Prepare context for the conversation agent
            context_parts = []
            context_parts.append(f"USER QUESTION: {original_query}")

            # Add conversation history context if this is a follow-up
            if conversation_context:
                recent_context = []
                for msg in reversed(conversation_context[-4:]):  # Last 2 exchanges
                    if msg.message_type == "user":
                        recent_context.append(f"User previously asked: {msg.content}")
                    elif msg.message_type == "assistant":
                        recent_context.append(
                            f"I previously responded about: {msg.content[:150]}..."
                        )
                    if len(recent_context) >= 4:  # 2 exchanges max
                        break

                if recent_context:
                    context_parts.append("\nCONVERSATION HISTORY:")
                    context_parts.extend(reversed(recent_context))

            context_parts.append("\nRETRIEVED LORE INFORMATION:")

            # Add chunk information
            for i, chunk in enumerate(rag_result["chunks"][:5], 1):  # Top 5 chunks
                context_parts.append(f"\nSource {i} (Relevance: {chunk['similarity']:.2f}):")
                context_parts.append(chunk["text"])

            # Add entity information if available (now with rich properties)
            if rag_result.get("entities"):
                context_parts.append("\nRELATED ENTITIES FOUND (with properties):")
                for entity in rag_result["entities"][:5]:  # Top 5 entities
                    entity_desc = f"- {entity['name']} ({entity['type']})"

                    # Add entity description if available
                    if entity.get("description"):
                        entity_desc += f": {entity['description']}"

                    # Add metadata if available from Graphiti
                    if entity.get("metadata"):
                        properties = []
                        for key, value in entity["metadata"].items():
                            # Skip technical fields, include meaningful ones
                            if key not in ["uuid", "group_id", "created_at", "name_embedding"]:
                                if (
                                    value
                                    and str(value).strip()
                                    and str(value) not in ["null", "NULL", "None"]
                                ):
                                    properties.append(f"{key}: {value}")

                        if properties:
                            entity_desc += f" [{', '.join(properties[:3])}]"  # Limit to 3 properties to avoid clutter

                    context_parts.append(entity_desc)

            # Add relationship information if available (now with rich semantic properties)
            if rag_result.get("relationships"):
                context_parts.append("\nKNOWN RELATIONSHIPS (with semantic properties):")
                for rel in rag_result["relationships"][:5]:  # Top 5 relationships
                    # Basic relationship info
                    rel_desc = f"- {rel['target_name']} ({rel['target_type']}) - {rel['type']}"

                    # Add rich semantic properties if available from Graphiti
                    if rel.get("metadata"):
                        properties = []
                        for key, value in rel["metadata"].items():
                            # Skip technical fields, include semantic ones
                            if key not in [
                                "uuid",
                                "group_id",
                                "created_at",
                                "target_node_uuid",
                                "source_node_uuid",
                                "episodes",
                            ]:
                                if (
                                    value
                                    and str(value).strip()
                                    and str(value) not in ["null", "NULL", "None"]
                                ):
                                    properties.append(f"{key}: {value}")

                        if properties:
                            # Let the LLM interpret these properties naturally
                            rel_desc += f" [{', '.join(properties)}]"

                context_parts.append(rel_desc)

            # Enhanced prompt for context awareness and property interpretation
            context_parts.append(
                "\nIMPORTANT: The entities and relationships above include rich semantic properties in brackets (e.g., [strength: strong, cosmic_role: protective omen]). These properties were extracted by AI to provide deeper context about the nature of each relationship. Please interpret these properties naturally in your response to provide richer, more nuanced information."
            )

            if conversation_context and any(
                indicator in original_query.lower()
                for indicator in ["that", "this", "more", "continue"]
            ):
                context_parts.append(
                    "\nThe user is asking a follow-up question referring to our previous conversation. Please provide a conversational response that builds on what we discussed earlier while incorporating the new information retrieved, using the semantic properties to add depth and context."
                )
            else:
                context_parts.append(
                    f"\nPlease provide a conversational, engaging response about '{original_query}' based on this information, using the semantic properties to enrich your narrative."
                )

            full_context = "\n".join(context_parts)

            # Use the conversation agent to generate a proper response
            try:
                self.logger.info(
                    f"Calling conversation agent with context length: {len(full_context)}"
                )
                result = await self.conversation_agent.run(full_context)
                self.logger.info("Conversation agent succeeded (%s)", type(result).__name__)
                return result.output
            except Exception as e:
                self.logger.error("Conversation agent failed (%s)", type(e).__name__)
                return public_error_message("Conversation agent")

        except Exception as e:
            self.logger.error("Error processing message (%s)", type(e).__name__)
            return public_error_message("Message processing")

    def _build_context_aware_query(
        self, current_message: str, context: list[ConversationMessage], conversation_id: str
    ) -> str:
        """Build a graph-aware query using entity tracking and conversation history."""
        if not context:
            return current_message

        # First, check if query is correlated with recent conversation
        is_correlated, correlation_score = self._check_query_correlation(current_message, context)

        # Only enhance if there's actual correlation (not just any follow-up)
        if not is_correlated:
            self.logger.info("No query correlation detected (score %.2f)", correlation_score)
            return current_message

        # Check if this is a follow-up question (contains pronouns or vague references)
        follow_up_indicators = [
            "that",
            "this",
            "it",
            "they",
            "them",
            "more about",
            "tell me more",
            "what else",
            "continue",
            "go on",
            "expand on",
        ]
        is_follow_up = any(
            indicator in current_message.lower() for indicator in follow_up_indicators
        )

        if not is_follow_up:
            return current_message

        # Get or create entity tracker for this conversation
        if conversation_id not in self.conversation_trackers:
            self.conversation_trackers[conversation_id] = ConversationEntityTracker()

        tracker = self.conversation_trackers[conversation_id]

        # Get recently discussed entities (last 3 messages)
        recent_entities = tracker.get_recent_entities(last_n_messages=3)

        if not recent_entities:
            # Fall back to text-based topic extraction
            return self._build_text_based_query(current_message, context)

        # Build entity-enhanced query
        entity_names = []
        entity_types = []

        # Use top 3 most relevant recent entities
        for entity in recent_entities[:3]:
            if entity["name"]:
                entity_names.append(entity["name"])
            if entity["type"] and entity["type"] not in entity_types:
                entity_types.append(entity["type"])

        # For very vague follow-ups like "tell me more", be more explicit
        vague_indicators = ["tell me more", "more about that", "what else", "continue", "go on"]
        if any(indicator in current_message.lower() for indicator in vague_indicators):
            if entity_names:
                # Replace vague reference with specific entity names
                enhanced_query = f"{' '.join(entity_names)} {current_message.replace('that', '').replace('it', '').strip()}"
                self.logger.info(
                    "Enhanced vague query from %d tracked entities (score %.2f)",
                    len(entity_names),
                    correlation_score,
                )
                return enhanced_query

        # For other follow-ups, add entity context
        if entity_names:
            enhanced_query = f"{' '.join(entity_names)} {current_message}"
            self.logger.info(
                "Enhanced follow-up query from %d tracked entities (score %.2f)",
                len(entity_names),
                correlation_score,
            )
            return enhanced_query

        # Fall back to text-based enhancement
        return self._build_text_based_query(current_message, context)

    def _build_text_based_query(
        self, current_message: str, context: list[ConversationMessage]
    ) -> str:
        """Fallback text-based query enhancement when no entity tracking available."""
        # Get the most recent assistant response to understand the main topic
        last_assistant_response = None
        last_user_message = None

        for msg in reversed(context):
            if msg.message_type == "assistant" and not last_assistant_response:
                last_assistant_response = msg.content
            elif msg.message_type == "user" and not last_user_message:
                last_user_message = msg.content
            if last_assistant_response and last_user_message:
                break

        if not last_assistant_response:
            return current_message

        # Extract main topics from the last assistant response
        import re

        # Look for key topic words (capitalized entities and important terms)
        topic_patterns = [
            r"\b(Age|Ages?)\s+of\s+\w+",  # "Age of X" patterns
            r"\b(Timeline|History|Chronicle|Era)\b",  # Timeline-related words
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b",  # Capitalized entities
        ]

        topic_matches = []
        for pattern in topic_patterns:
            matches = re.findall(pattern, last_assistant_response, re.IGNORECASE)
            topic_matches.extend(matches)

        # Also extract key terms from the last user message to understand what they originally asked about
        if last_user_message:
            user_keywords = [
                word
                for word in last_user_message.lower().split()
                if len(word) > 3
                and word not in {"the", "a", "an", "and", "or", "but", "about", "tell", "what"}
            ]
            topic_matches.extend(user_keywords[:3])

        # Build enhanced query
        if topic_matches:
            unique_topics = list(dict.fromkeys(str(topic).lower() for topic in topic_matches))[:5]
            enhanced_query = f"{' '.join(unique_topics)} {current_message}"
            self.logger.info("Enhanced follow-up query from %d topics", len(unique_topics))
        else:
            enhanced_query = current_message

        return enhanced_query

    def _generate_semantic_thinking(self, rag_result: dict[str, Any]) -> str:
        """Generate thinking content showing how semantic data is being used."""
        thinking_parts = []

        # Show retrieved content overview
        chunks = rag_result.get("chunks", [])
        entities = rag_result.get("entities", [])
        relationships = rag_result.get("relationships", [])

        thinking_parts.append(f"Found {len(chunks)} relevant text chunks")

        if entities:
            thinking_parts.append(f"and {len(entities)} entities")

            # Show interesting entity types
            entity_types = {}
            for entity in entities[:5]:
                entity_type = entity.get("type", "Unknown")
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

            if entity_types:
                type_summary = [
                    f"{count} {type_name.lower()}{'s' if count > 1 else ''}"
                    for type_name, count in sorted(entity_types.items())
                ]
                thinking_parts.append(f"({', '.join(type_summary)})")

        if relationships:
            thinking_parts.append(f"with {len(relationships)} connections")

            # Show interesting relationship properties
            semantic_props = set()
            for rel in relationships[:10]:  # Check top 10 relationships
                metadata = rel.get("metadata", {})
                if metadata and isinstance(metadata, dict):  # Null check
                    for key, value in metadata.items():
                        if key not in ["source_entity_type", "target_entity_type"] and value:
                            semantic_props.add(f"{key}: {value}")

            if semantic_props:
                # Show a few interesting properties
                prop_list = list(semantic_props)[:3]
                thinking_parts.append(f"including semantic properties like {', '.join(prop_list)}")

        return "Analyzing " + " ".join(thinking_parts) + "..."

    def _check_query_correlation(
        self, current_message: str, context: list[ConversationMessage]
    ) -> tuple[bool, float]:
        """Check if current query is correlated with recent conversation context."""
        if not context:
            return False, 0.0

        # Get the last assistant response to understand previous topic
        last_assistant_msg = None
        for msg in reversed(context):
            if msg.message_type == "assistant":
                last_assistant_msg = msg
                break

        if not last_assistant_msg:
            return False, 0.0

        # Simple correlation indicators
        current_lower = current_message.lower()

        # Strong correlation indicators (pronouns and direct references)
        strong_indicators = ["that", "this", "it", "they", "them", "he", "she", "those", "these"]
        has_strong_correlation = any(
            indicator in current_lower.split() for indicator in strong_indicators
        )

        # Weak correlation indicators (continuation phrases)
        weak_indicators = [
            "tell me more",
            "what else",
            "continue",
            "expand on",
            "also",
            "additionally",
        ]
        has_weak_correlation = any(indicator in current_lower for indicator in weak_indicators)

        # Topic shift indicators (new topics)
        shift_indicators = [
            "now tell me about",
            "what about",
            "switch to",
            "instead tell me",
            "now about",
        ]
        has_topic_shift = any(indicator in current_lower for indicator in shift_indicators)

        # Calculate correlation score
        correlation_score = 0.0

        if has_topic_shift:
            correlation_score -= 0.8  # Strong negative correlation

        if has_strong_correlation:
            correlation_score += 0.8
        elif has_weak_correlation:
            correlation_score += 0.5

        # Check if query is very different in nature (new proper nouns)
        import re

        current_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", current_message)
        last_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", last_assistant_msg.content)

        entity_overlap = len(set(current_entities) & set(last_entities))
        total_entities = len(set(current_entities) | set(last_entities))

        if total_entities > 0:
            entity_similarity = entity_overlap / total_entities
            correlation_score += entity_similarity * 0.3

        # Final correlation decision
        is_correlated = correlation_score > 0.3

        return is_correlated, max(0.0, min(1.0, correlation_score))

    def _track_conversation_entities(
        self, conversation_id: str, rag_result: dict[str, Any], message_index: int, query: str = ""
    ):
        """Track entities and relationships from RAG results for conversation context."""
        # Get or create entity tracker for this conversation
        if conversation_id not in self.conversation_trackers:
            self.conversation_trackers[conversation_id] = ConversationEntityTracker()

        tracker = self.conversation_trackers[conversation_id]

        # Add entities
        if rag_result.get("entities"):
            tracker.add_entities(rag_result["entities"], message_index)

        # Add relationships
        if rag_result.get("relationships"):
            tracker.add_relationships(rag_result["relationships"])

        # Track response patterns for exhaustion detection
        chunks = rag_result.get("chunks", [])
        if chunks:
            tracker.track_response(chunks, query, message_index)

    def _is_graph_content_relevant(self, rag_result: dict[str, Any], conversation_id: str) -> bool:
        """Check if retrieved content is relevant using graph entity relationships."""
        if conversation_id not in self.conversation_trackers:
            return True  # No tracking available, assume relevant

        tracker = self.conversation_trackers[conversation_id]
        recent_entities = tracker.get_recent_entities(last_n_messages=3)

        if not recent_entities:
            return True  # No recent entities to compare against

        # Extract entity IDs from recent conversation
        recent_entity_ids = {e["id"] for e in recent_entities}
        recent_entity_names = {e["name"].lower() for e in recent_entities if e["name"]}

        # Check if any retrieved entities match or are related to recent entities
        retrieved_entities = rag_result.get("entities", [])

        for entity in retrieved_entities:
            entity_id = entity.get("stable_id") or entity.get("id")
            entity_name = entity.get("name", "").lower()

            # Direct entity match
            if entity_id in recent_entity_ids or entity_name in recent_entity_names:
                return True

            # Check if entity is related to any recent entity
            if entity_id:
                for recent_entity in recent_entities:
                    recent_id = recent_entity["id"]
                    related_entities = tracker.get_related_entities(recent_id)
                    if entity_id in related_entities:
                        return True

        # Check relationships for indirect connections
        relationships = rag_result.get("relationships", [])
        for rel in relationships:
            source_id = rel.get("source")
            target_id = rel.get("target")

            if source_id in recent_entity_ids or target_id in recent_entity_ids:
                return True

        # Check if chunk text mentions recent entities (fallback)
        chunks = rag_result.get("chunks", [])
        for chunk in chunks[:3]:  # Check top 3 chunks
            chunk_text = chunk.get("text", "").lower()
            for entity_name in recent_entity_names:
                if entity_name and len(entity_name) > 2 and entity_name in chunk_text:
                    return True

        # No relevance found
        return False

    def _extract_recent_topics(self, context: list[ConversationMessage]) -> list[str]:
        """Extract key topics from recent conversation."""
        topics = []

        # Look at the last assistant response to understand what was discussed
        for msg in reversed(context[-2:]):  # Last 2 messages
            if msg.message_type == "assistant":
                import re

                # Extract key terms and entities
                content = msg.content.lower()

                # Look for specific topic indicators
                topic_patterns = [
                    r"\b(age|ages?)\s+of\s+[\w\s]+",
                    r"\b(timeline|history|chronicle|era)\b",
                    r"\b(magic|spell|wizard|arcane)\b",
                    r"\b(knight|order|faction)\b",
                    r"\b(geography|location|realm)\b",
                    r"\b(deity|god|goddess|divine)\b",
                ]

                for pattern in topic_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    topics.extend(matches)

                break  # Only need the most recent assistant response

        return [topic.strip() for topic in topics if len(topic.strip()) > 2]

    def _is_content_relevant(self, chunks: list[dict], recent_topics: list[str]) -> bool:
        """Check if retrieved content chunks are relevant to recent conversation topics."""
        if not recent_topics or not chunks:
            return True  # If no topics to compare against, assume relevant

        # Convert topics to lowercase for comparison
        topic_keywords = set()
        for topic in recent_topics:
            topic_keywords.update(word.lower() for word in topic.split() if len(word) > 2)

        # Check if any chunks contain the topic keywords
        for chunk in chunks[:3]:  # Check top 3 chunks
            chunk_text = chunk.get("text", "").lower()

            # If at least 2 topic keywords appear in the chunk, consider it relevant
            matching_keywords = sum(1 for keyword in topic_keywords if keyword in chunk_text)
            if matching_keywords >= 2:
                return True

        return False

    async def _stream_response_content(self, content: str) -> AsyncGenerator[StreamEvent, None]:
        """Stream response content in chunks."""
        # Split content into sentences for natural streaming
        sentences = content.split(". ")

        for i, sentence in enumerate(sentences):
            if i < len(sentences) - 1:
                sentence += ". "  # Re-add the period

            yield StreamEvent(type=StreamEventType.CONTENT, content=sentence)

            # Small delay for natural streaming feel
            await asyncio.sleep(0.1)

    def _extract_sources(self, rag_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract source information from RAG results."""
        sources = []

        for chunk in rag_result.get("chunks", []):
            sources.append(
                {
                    "type": "episode",
                    "document_id": chunk.get("document_id"),
                    "similarity": chunk.get("similarity", 0.0),
                    "text_preview": chunk.get("text", "")[:200],
                }
            )

        return sources

    def _generate_follow_ups(
        self, intent_result: IntentClassification, response_data: dict[str, Any]
    ) -> list[str]:
        """Generate suggested follow-up questions."""
        suggestions = []

        entities = response_data.get("entities_found", [])

        if entities:
            entity = entities[0]
            suggestions.append(f"Tell me more about {entity['name']}")
            suggestions.append(f"What relationships does {entity['name']} have?")

        if intent_result.intent == QueryIntent.QUESTION:
            suggestions.extend(
                ["Can you expand on that?", "What else should I know about this topic?"]
            )
        elif intent_result.intent == QueryIntent.EXPLORATION:
            suggestions.extend(
                ["Show me related entities", "What historical events involve these entities?"]
            )

        return suggestions[:4]  # Limit to 4 suggestions
