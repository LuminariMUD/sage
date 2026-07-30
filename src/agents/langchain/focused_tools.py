"""Focused, single-purpose tools for ReAct agent.

Each tool does ONE thing well with clear, specific parameters.
This follows ReAct best practices for tool design.
"""

import asyncio
import json
import logging
from typing import Any

from langchain_core.tools import tool

from src.llm.langchain_helpers import get_chat_model
from src.security import public_error_message

from .chains.retrieval import RetrievalChain
from .story_workflow import StoryWorkflow

logger = logging.getLogger(__name__)


def extract_json_from_markdown(content: str) -> str:
    """Extract JSON from markdown code blocks if present."""
    if "```json" in content:
        return content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    return content


def _normalize_context_entry(entry: Any) -> str:
    """Convert mixed context payloads into plain text snippets."""

    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        entity = entry.get("entity") or entry.get("name")
        descriptor = entry.get("description") or entry.get("summary") or entry.get("details")
        if entity and descriptor:
            return f"ENTITY {entity}: {descriptor}"
        try:
            return json.dumps(entry, ensure_ascii=False)
        except Exception:  # pragma: no cover - fallback for non-serializable entries
            return str(entry)
    return str(entry)


@tool
async def search_lore(query: str) -> dict[str, Any]:
    """Search Luminari lore database for information. Use this FIRST before creating content.

    WHEN TO USE: Before any content creation to get canonical information.

    GOOD EXAMPLES:
    - query: "Crystal Dwarves culture and society"
    - query: "Mark of the Luminari meaning and significance"
    - query: "Mosswood forest description"

    BAD EXAMPLES (too vague):
    - query: "stuff"
    - query: "everything about everything"

    Returns:
        Dict with context_blocks, entities, relationships, and metadata
    """

    retrieval = RetrievalChain()

    def _generate_followup_queries(primary: str) -> list[str]:
        lowered = primary.lower().strip()
        cleaned = lowered.rstrip("?!., ")
        followups: list[str] = []

        # Extract subject by removing leading question words/auxiliaries
        words_to_strip = [
            "who",
            "what",
            "where",
            "when",
            "why",
            "how",
            "which",
            "tell me about",
            "describe",
            "explain",
        ]
        for prefix in words_to_strip:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                break

        auxiliaries = [
            "is",
            "are",
            "was",
            "were",
            "do",
            "does",
            "did",
            "can",
            "could",
            "should",
            "would",
            "leads",
            "lead",
            "run",
            "runs",
            "controls",
            "control",
            "command",
            "commands",
        ]
        for aux in auxiliaries:
            if cleaned.startswith(aux + " "):
                cleaned = cleaned[len(aux) + 1 :].strip()

        cleaned = cleaned.strip(" ?!.,")

        if not cleaned:
            return []

        base_variants = [cleaned]
        if cleaned.startswith(("the ", "a ", "an ")):
            base_variants.append(cleaned.split(" ", 1)[1])

        return [q for q in followups if q]

    queries: list[str] = [query]
    queries.extend(_generate_followup_queries(query))
    # Deduplicate while preserving order
    seen_queries = set()
    ordered_queries = []
    for q in queries:
        q_norm = q.strip()
        if q_norm and q_norm.lower() not in seen_queries:
            ordered_queries.append(q_norm)
            seen_queries.add(q_norm.lower())

    primary_query = ordered_queries[0] if ordered_queries else query
    primary_terms = {
        token.strip(" ,.!?\"'")
        for token in primary_query.lower().split()
        if token.strip(" ,.!?\"'") and len(token) > 2
    }

    aggregated_chunks: list[dict[str, Any]] = []
    aggregated_context: list[str] = []
    aggregated_entities: list[dict[str, Any]] = []
    aggregated_relationships: list[dict[str, Any]] = []
    graph_entity_by_uuid: dict[str, dict[str, Any]] = {}
    graph_relationship_seen: set = set()
    chunk_text_seen = set()

    aggregated_raw = {
        "queries": ordered_queries,
        "chunks": [],
        "entities": [],
        "relationships": [],
        "metadata": {},
    }

    for q in ordered_queries:
        result = await retrieval.ainvoke({"query": q})

        raw_data = result.get("raw", {}) or {}

        for chunk in raw_data.get("chunks", []):
            text = chunk.get("text", "")
            if text and text not in chunk_text_seen:
                aggregated_raw["chunks"].append(chunk)
                chunk_text_seen.add(text)
                aggregated_chunks.append(chunk)

        for ent in raw_data.get("entities", []) or []:
            if isinstance(ent, dict) and ent.get("name"):
                if ent not in aggregated_entities:
                    aggregated_entities.append(ent)

        for rel in raw_data.get("relationships", []) or []:
            if isinstance(rel, dict) and rel not in aggregated_relationships:
                aggregated_relationships.append(rel)

        metadata_block = raw_data.get("metadata") or {}
        for graph_entity in metadata_block.get("graph_entities", []) or []:
            if isinstance(graph_entity, dict):
                gid = graph_entity.get("uuid") or graph_entity.get("id")
                if gid and gid not in graph_entity_by_uuid:
                    graph_entity_by_uuid[gid] = graph_entity
        for graph_rel in metadata_block.get("graph_relationships", []) or []:
            if isinstance(graph_rel, dict):
                key = (
                    graph_rel.get("source"),
                    graph_rel.get("target"),
                    graph_rel.get("type"),
                    (
                        graph_rel.get("metadata", {}).get("fact")
                        if graph_rel.get("metadata")
                        else graph_rel.get("fact")
                    ),
                )
                if key not in graph_relationship_seen:
                    graph_relationship_seen.add(key)
                    aggregated_raw.setdefault("metadata", {}).setdefault(
                        "graph_relationships", []
                    ).append(graph_rel)

    # Limit entities/relationships
    # Rank chunks by similarity and overlap with primary query terms
    def chunk_score(chunk: dict[str, Any]) -> float:
        base = float(chunk.get("similarity") or chunk.get("score") or 0.0)
        text = (chunk.get("text", "") or "").lower()
        overlap = sum(1 for term in primary_terms if term and term in text)
        return base + 0.05 * overlap

    top_chunks = sorted(aggregated_chunks, key=chunk_score, reverse=True)[:18]

    aggregated_entities = aggregated_entities[:10]
    aggregated_relationships = aggregated_relationships[:10]

    aggregated_raw["entities"] = aggregated_entities
    aggregated_raw["relationships"] = aggregated_relationships
    if graph_entity_by_uuid:
        aggregated_raw["metadata"]["graph_entities"] = list(graph_entity_by_uuid.values())[:12]
    elif "metadata" in aggregated_raw and not aggregated_raw["metadata"]:
        aggregated_raw.pop("metadata")

    ordered_context: list[str] = []
    seen_texts = set()

    def add_context_block(text: str):
        trimmed = text.strip()
        if trimmed and trimmed not in seen_texts and len(ordered_context) < 40:
            ordered_context.append(trimmed)
            seen_texts.add(trimmed)

    # Add top-ranked text chunks (interleaving graph insights later)
    for chunk in top_chunks[:10]:
        add_context_block(chunk.get("text", ""))

    graph_insight_blocks: list[str] = []
    metadata = aggregated_raw.get("metadata", {}) or {}
    for ent in (metadata.get("graph_entities") or [])[:6]:
        if isinstance(ent, dict):
            name = ent.get("name")
            etype = ent.get("type") or "Entity"
            desc = ent.get("description") or ""
            attr = (
                ent.get("metadata", {}).get("attributes", {})
                if isinstance(ent.get("metadata"), dict)
                else {}
            )
            attr_text = "; ".join(
                f"{k.replace('_', ' ').title()}: {v}"
                for k, v in attr.items()
                if v not in (None, "", [])
            )
            summary = ", ".join(filter(None, [desc.strip(), attr_text.strip()]))
            if name and summary:
                graph_insight_blocks.append(f"GRAPH ENTITY {name} ({etype}): {summary}")

    for rel in (metadata.get("graph_relationships") or [])[:8]:
        if isinstance(rel, dict):
            r_type = rel.get("type", "related_to")
            source = rel.get("source", "?")
            target = rel.get("target", "?")
            meta = rel.get("metadata", {}) if isinstance(rel.get("metadata"), dict) else {}
            fact = meta.get("fact") or rel.get("fact", "")
            attr = meta.get("attributes", {}) if isinstance(meta.get("attributes"), dict) else {}
            attr_text = "; ".join(
                f"{k.replace('_', ' ').title()}: {v}"
                for k, v in attr.items()
                if v not in (None, "", [])
            )
            insight = "; ".join(filter(None, [fact, attr_text]))
            if insight:
                graph_insight_blocks.append(
                    f"GRAPH RELATIONSHIP {r_type} ({source} -> {target}): {insight}"
                )

    for block in graph_insight_blocks:
        add_context_block(block)

    async def _fetch_relationship_summaries(
        entity: dict[str, Any],
        search_terms: set[str],
        max_relationships: int = 6,
    ) -> list[str]:
        """Fetch relationship summaries for an entity via the internal API."""

        import os

        import httpx

        entity_uuid = entity.get("uuid")
        entity_name = entity.get("name") or entity.get("summary") or "Unknown"
        if not entity_uuid:
            return []

        base_url = os.getenv("LANGCHAIN_INTERNAL_API_BASE", "http://localhost:8003").rstrip("/")
        headers = {}
        api_key = os.getenv("SAGE_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key

        summaries: list[str] = []

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                rel_list_resp = await client.get(
                    f"{base_url}/api/v1/entities/{entity_uuid}/relationships",
                    params={"limit": max_relationships * 3},
                    headers=headers,
                )
                rel_list_resp.raise_for_status()
                rel_list = rel_list_resp.json().get("relationships", [])
            except Exception as exc:  # pragma: no cover - network issues
                logger.debug("Relationship list fetch failed (%s)", type(exc).__name__)
                return []

            ranked: list[tuple[float, dict[str, Any]]] = []
            for rel in rel_list:
                rel_type = rel.get("relationship_type", "")
                rel_tokens = {part.lower() for part in rel_type.replace("_", " ").split()}
                overlap = len(rel_tokens & search_terms)

                peer_name = rel.get("target_name") or rel.get("source_name") or ""
                if peer_name:
                    peer_tokens = {token.lower() for token in peer_name.split()}
                    overlap += len(peer_tokens & search_terms)

                ranked.append((overlap, rel))

            ranked.sort(key=lambda item: item[0], reverse=True)
            selected = [item[1] for item in ranked[: max_relationships * 2]]

            for rel in selected:
                rel_id = rel.get("relationship_id")
                if rel_id is None:
                    continue

                try:
                    details_resp = await client.get(
                        f"{base_url}/api/v1/relationships/{rel_id}", headers=headers
                    )
                    details_resp.raise_for_status()
                    details = details_resp.json()
                except Exception as exc:  # pragma: no cover - network issues
                    logger.debug(
                        "Relationship detail fetch failed for %s (%s): %s",
                        entity_name,
                        rel_id,
                        exc,
                    )
                    continue

                rel_type = details.get(
                    "relationship_type", rel.get("relationship_type", "related_to")
                )
                source = details.get("source", {})
                target = details.get("target", {})
                properties = details.get("properties", {}) or {}

                direction = "->"
                source_name = source.get("name", entity_name)
                target_name = target.get(
                    "name", rel.get("target_name") or rel.get("source_name") or "Unknown"
                )

                if rel.get("direction") == "incoming" and source_name != entity_name:
                    direction = "<-"
                elif rel.get("direction") == "incoming" and source_name == entity_name:
                    direction = "<-"
                elif source_name == entity_name and target_name != entity_name:
                    direction = "->"
                else:
                    direction = "<-" if rel.get("direction") == "incoming" else "->"

                friendly_type = rel_type.replace("_", " ").replace("-", " ")
                friendly_type = " ".join(part.capitalize() for part in friendly_type.split())

                fact = (
                    properties.get("fact")
                    or properties.get("description")
                    or properties.get("details")
                )
                if not fact:
                    for value in properties.values():
                        if isinstance(value, str) and len(value) <= 220:
                            fact = value
                            break

                summary = (
                    f"GRAPH RELATIONSHIP {friendly_type} ({source_name} {direction} {target_name})"
                )
                if fact:
                    summary += f": {fact}"

                summaries.append(summary)
                if len(summaries) >= max_relationships:
                    break

        return summaries

    relationship_summary_blocks: list[str] = []

    if aggregated_entities:
        term_set = {term for term in primary_terms if term}
        tasks = [
            _fetch_relationship_summaries(entity, term_set)
            for entity in aggregated_entities[:3]
            if entity.get("uuid")
        ]

        if tasks:
            relationship_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in relationship_results:
                if isinstance(result, Exception):
                    continue
                relationship_summary_blocks.extend(result)

    for block in relationship_summary_blocks[:15]:
        add_context_block(block)

    # Surface top entity summaries so the agent has direct access to canonical blurbs
    entity_summary_blocks: list[str] = []
    for ent in aggregated_entities[:6]:
        name = ent.get("name")
        summary = ent.get("summary") or ent.get("description")
        if name and summary:
            entity_summary_blocks.append(f"ENTITY {name}: {summary}")

    for block in entity_summary_blocks:
        add_context_block(block)

    for chunk in top_chunks[10:]:
        add_context_block(chunk.get("text", ""))

    return {
        "context_blocks": ordered_context,
        "entities": [
            {
                "name": ent.get("name", ""),
                "type": ent.get("type", ""),
                "summary": ent.get("summary") or ent.get("description", ""),
                "uuid": ent.get("uuid", ""),
                "metadata": ent.get("metadata", {}),
            }
            for ent in aggregated_entities
        ],
        "relationships": [
            {
                "type": rel.get("type", ""),
                "target": rel.get("target_name", ""),
                "fact": rel.get("metadata", {}).get("fact", "") if rel.get("metadata") else "",
                "strength": rel.get("strength", 1),
                "metadata": rel.get("metadata", {}),
            }
            for rel in aggregated_relationships
        ],
        "entity_count": len(aggregated_entities),
        "relationship_count": len(aggregated_relationships),
        "found": bool(aggregated_context),
        "metadata": {
            "chunks_found": len(aggregated_raw["chunks"]),
            "queries_used": ordered_queries,
            "graph_entity_count": len(graph_entity_by_uuid),
            "graph_relationship_count": (
                len(aggregated_raw.get("metadata", {}).get("graph_relationships", []))
                if aggregated_raw.get("metadata")
                else 0
            ),
            "relationship_summary_count": len(relationship_summary_blocks),
        },
        "raw": aggregated_raw,
    }


@tool
async def answer_lore_question(question: str, context: list[Any] | None = None) -> dict[str, Any]:
    """Answer a lore question using canonical context from search_lore.

    The tool prefers rich context supplied by ``search_lore`` but will fall back
    to an internal retrieval pass when none is provided. It returns the
    synthesized answer alongside the context digest and source metadata so the
    calling agent can inspect coverage.
    """

    from .chains.direct_answer import DirectAnswerChain
    from .chains.retrieval import RetrievalChain

    if not question or not question.strip():
        return {
            "answer": "The archives require a clear question before an answer can be composed.",
            "used_context_blocks": 0,
            "source_blocks": [],
            "context_digest": {},
        }

    def _normalize(raw_blocks: list[Any] | None) -> list[str]:
        normalised: list[str] = []
        seen: set[str] = set()
        if not raw_blocks:
            return normalised
        for block in raw_blocks:
            text: str | None = None
            if isinstance(block, str):
                text = block
            elif isinstance(block, dict):
                for key in ("text", "content", "summary", "chunk", "body"):
                    value = block.get(key)
                    if isinstance(value, str) and value.strip():
                        text = value
                        break
            if not text:
                continue
            trimmed = text.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalised.append(trimmed)
            if len(normalised) >= 20:
                break
        return normalised

    context_blocks = _normalize(context)
    retrieval_metadata: dict[str, Any] | None = None

    if not context_blocks:
        retrieval = RetrievalChain()
        retrieval_result = await retrieval.ainvoke({"query": question})
        context_blocks = _normalize(retrieval_result.get("context_blocks"))
        raw = retrieval_result.get("raw") or {}
        metadata = raw.get("metadata") or {}
        retrieval_metadata = {
            "chunks_found": len(raw.get("chunks", [])) if isinstance(raw, dict) else 0,
            "graph_entities": (
                len(metadata.get("graph_entities", [])) if isinstance(metadata, dict) else 0
            ),
            "graph_relationships": (
                len(metadata.get("graph_relationships", [])) if isinstance(metadata, dict) else 0
            ),
            "queries_used": retrieval_result.get("query"),
        }

    chain = DirectAnswerChain(enable_reflection=False)
    result = chain.invoke(
        {
            "query": question,
            "context_blocks": context_blocks,
        }
    )

    payload: dict[str, Any] = {
        "answer": result.get("answer", "The archives produced no response."),
        "used_context_blocks": result.get("used_blocks", len(context_blocks)),
        "source_blocks": result.get("source_blocks", []),
        "context_digest": result.get("context_digest", {}),
        "digest_text": result.get("digest_text"),
        "context_blocks": context_blocks,
        "question": question,
    }

    if retrieval_metadata:
        payload["retrieval_metadata"] = retrieval_metadata

    return payload


@tool
async def create_quest_hook(
    premise: str, location: str, hook_type: str = "discovery"
) -> dict[str, str]:
    """Create ONLY the quest introduction/hook. Call this ONCE per quest.

    WHEN TO USE: After searching lore, as the FIRST step of quest creation.

    GOOD EXAMPLE:
    - premise: "investigating strange disappearances in the market"
    - location: "Ashenport marketplace"
    - hook_type: "mysterious"

    Returns:
        Dict with hook_text and initial_objective
    DO NOT call this multiple times for the same quest!
    """
    llm = get_chat_model(task="creative", temperature=0.8, streaming=False)

    prompt = f"""Create a quest hook for LuminariMUD.

Premise: {premise}
Starting Location: {location}
Hook Type: {hook_type}

Write a compelling 2-3 paragraph quest hook that draws players in.
Include the initial objective.

Output as JSON:
{{"hook_text": "...", "initial_objective": "..."}}"""

    response = await llm.ainvoke(prompt)
    content = extract_json_from_markdown(response.content)

    try:
        result = json.loads(content)
        # Ensure required fields exist
        if "hook_text" not in result:
            result["hook_text"] = content
        if "initial_objective" not in result:
            result["initial_objective"] = "Investigate the situation"
        return result
    except Exception:
        # Fallback if still can't parse
        return {"hook_text": content, "initial_objective": "Investigate the situation"}


@tool
async def create_quest_phase(
    phase_name: str,
    objective: str,
    previous_phase: str | None = None,
    include_combat: bool = False,
    quest_context: str | None = None,
    maintain_continuity: str | None = None,
) -> dict[str, Any]:
    """Create ONE quest phase. Call multiple times (3-5) for a complete quest.

    WHEN TO USE: After creating the hook, call 3-5 times with DIFFERENT phase names.

    GOOD SEQUENCE:
    1. phase_name: "Investigation", objective: "Gather clues about the disappearances"
    2. phase_name: "Discovery", objective: "Find the source of the problem"
    3. phase_name: "Confrontation", objective: "Face the antagonist"
    4. phase_name: "Resolution", objective: "Resolve the situation"

    Returns:
        Dict with phase_description, npcs, challenges, completion_trigger
    """
    llm = get_chat_model(task="creative", temperature=0.7, streaming=False)

    continuity = f"\nContinuing from: {previous_phase}" if previous_phase else ""
    combat = "\nInclude a combat encounter." if include_combat else ""
    context = f"\n\nQUEST CONTEXT:\n{quest_context}" if quest_context else ""
    maintain = f"\n\nMAINTAIN CONTINUITY:\n{maintain_continuity}" if maintain_continuity else ""

    prompt = f"""Create a quest phase for LuminariMUD.

Phase Name: {phase_name}
Objective: {objective}{continuity}{combat}{context}{maintain}

IMPORTANT: Maintain consistency with character names, locations, and the overall narrative arc.

Create a detailed phase description (3-4 paragraphs) including:
- What happens in this phase
- NPCs involved (use the SAME names from previous phases)
- Challenges or obstacles
- How it advances the overall story
- How it connects to both the immediate objective AND the larger quest narrative

Output as JSON:
{{"phase_description": "...", "npcs": ["..."], "challenges": ["..."], "completion_trigger": "..."}}"""

    response = await llm.ainvoke(prompt)
    content = extract_json_from_markdown(response.content)

    try:
        return json.loads(content)
    except Exception:
        return {
            "phase_description": content,
            "npcs": [],
            "challenges": [],
            "completion_trigger": "Complete the objective",
        }


@tool
async def create_quest_reward(quest_title: str, difficulty: str, theme: str) -> dict[str, Any]:
    """Create appropriate rewards for completing a quest.

    Args:
        quest_title: Title of the quest
        difficulty: easy/medium/hard/epic
        theme: Quest theme (combat, mystery, exploration, social)

    Returns:
        Dict with rewards including items, experience, reputation
    """
    llm = get_chat_model(task="chat", temperature=0.7, streaming=False)

    prompt = f"""Create quest rewards for LuminariMUD.

Quest: {quest_title}
Difficulty: {difficulty}
Theme: {theme}

Create appropriate rewards including:
- Experience points
- Gold/currency
- 1-2 unique items with descriptions
- Reputation changes if relevant

Output as JSON:
{{"experience": 0, "gold": 0, "items": [{{"name": "...", "description": "..."}}], "reputation": {{"faction": "...", "change": 0}}}}"""

    response = await llm.ainvoke(prompt)
    content = extract_json_from_markdown(response.content)

    try:
        return json.loads(content)
    except Exception:
        return {
            "experience": 1000,
            "gold": 100,
            "items": [{"name": "Quest Reward", "description": "A reward for completing the quest"}],
            "reputation": {},
        }


@tool
async def create_npc(
    name: str, role: str, personality: str, location: str, lore_context: list[Any] | None = None
) -> dict[str, str]:
    """Create a detailed NPC (Non-Player Character).

    Args:
        name: NPC's name
        role: Their role/occupation
        personality: Key personality traits
        location: Where they can be found

    Returns:
        Dict with appearance, backstory, dialogue_style, and motivations
    """
    llm = get_chat_model(task="creative", temperature=0.8, streaming=False)

    context_section = ""
    if lore_context:
        normalized = [
            _normalize_context_entry(block) for block in lore_context if block is not None
        ]
        joined_context = "\n".join(entry.strip() for entry in normalized if entry and entry.strip())
        if joined_context:
            context_section = f"\nRelevant Lore:\n{joined_context[:1000]}\n"

    prompt = f"""Create an NPC for LuminariMUD.

Name: {name}
Role: {role}
Personality: {personality}
Location: {location}
{context_section}

Create a detailed NPC including:
- Physical appearance (2-3 sentences)
- Backstory (3-4 sentences)
- How they speak/dialogue style
- Their motivations and goals

Output as JSON:
{{"appearance": "...", "backstory": "...", "dialogue_style": "...", "motivations": "..."}}"""

    response = await llm.ainvoke(prompt)
    content = extract_json_from_markdown(response.content)

    try:
        return json.loads(content)
    except Exception:
        return {
            "appearance": "A typical resident",
            "backstory": content,
            "dialogue_style": "Normal speech",
            "motivations": "Unknown",
        }


@tool
async def create_location_description(
    location_name: str,
    environment_type: str,
    notable_features: list[str],
    lore_context: list[Any] | None = None,
) -> str:
    """Create a rich description for a location.

    Args:
        location_name: Name of the location
        environment_type: Type (forest, city, dungeon, etc.)
        notable_features: List of things that should be mentioned

    Returns:
        Atmospheric description of the location
    """
    llm = get_chat_model(task="creative", temperature=0.8, streaming=False)

    features = ", ".join(notable_features) if notable_features else "typical features"
    context_section = ""
    if lore_context:
        normalized = [
            _normalize_context_entry(block) for block in lore_context if block is not None
        ]
        joined_context = "\n".join(entry.strip() for entry in normalized if entry and entry.strip())
        if joined_context:
            context_section = f"\nRelevant Lore:\n{joined_context[:1200]}\n"

    prompt = f"""Create a location description for LuminariMUD.

Location: {location_name}
Type: {environment_type}
Notable Features: {features}
{context_section}

Write a rich, atmospheric description (3-4 paragraphs) that includes:
- Visual details
- Sounds and smells
- The feeling/mood of the place
- Points of interest

Focus on immersion and sensory details."""

    response = await llm.ainvoke(prompt)
    return response.content


@tool
async def create_story_opening(
    protagonist: str, setting: str, conflict: str, lore_context: list[Any] | None = None
) -> str:
    """Create the BEGINNING of a story. Call ONCE per story.

    WHEN TO USE: After searching lore, as the FIRST step for story creation.

    GOOD EXAMPLE:
    - protagonist: "young Crystal Dwarf outcast with clouded quartz form"
    - setting: "the underground crystal caverns of Nagburim"
    - conflict: "discovering their flaws might be a blessing, not a curse"

    Returns:
        Story opening (2-3 paragraphs)
    """
    llm = get_chat_model(task="creative", temperature=0.8, streaming=False)

    context_section = ""
    if lore_context:
        normalized = [
            _normalize_context_entry(block) for block in lore_context if block is not None
        ]
        joined_context = "\n".join(entry.strip() for entry in normalized if entry and entry.strip())
        if joined_context:
            context_section = f"\nRelevant Lore:\n{joined_context[:1200]}\n"

    prompt = f"""Write a story opening for the Luminari universe.

Protagonist: {protagonist}
Setting: {setting}
Conflict: {conflict}
{context_section}

Write an engaging opening (2-3 paragraphs) that:
- Introduces the protagonist naturally
- Establishes the setting vividly
- Hints at the conflict
- Creates intrigue to read more

Use rich, evocative language appropriate for fantasy fiction."""

    response = await llm.ainvoke(prompt)
    return response.content


@tool
async def continue_story(
    previous_section: str,
    what_happens_next: str,
    tone: str = "maintain",
    lore_context: list[Any] | None = None,
    story_brief: dict[str, Any] | None = None,
    cast: list[dict[str, Any]] | None = None,
) -> str:
    """Continue an EXISTING story. Only call AFTER create_story_opening.

    WHEN TO USE: To add more to a story you've already started.

    IMPORTANT: previous_section should be the last part of YOUR generated story, not the user's request!

    GOOD EXAMPLE:
    - previous_section: "...as she touched the crystal, visions flooded her mind."
    - what_happens_next: "she sees the truth about the Crystal Dwarves' transformation"
    - tone: "more_intense"

    Returns:
        Next section of the story
    """
    llm = get_chat_model(task="creative", temperature=0.8, streaming=False)

    context_section = ""
    if lore_context:
        normalized = [
            _normalize_context_entry(block) for block in lore_context if block is not None
        ]
        joined_context = "\n".join(entry.strip() for entry in normalized if entry and entry.strip())
        if joined_context:
            context_section = f"\nRelevant Lore:\n{joined_context[:1200]}\n"

    brief_snippet = ""
    if story_brief:
        try:
            brief_snippet = json.dumps(story_brief, ensure_ascii=False)
        except Exception:  # pragma: no cover - serialization fallback
            brief_snippet = str(story_brief)

    cast_snippet = ""
    if cast:
        try:
            cast_snippet = json.dumps(cast, ensure_ascii=False)
        except Exception:
            cast_snippet = str(cast)

    prompt = f"""Continue this Luminari story.

Previous section ended with:
...{previous_section[-500:]}

What happens next: {what_happens_next}
Tone adjustment: {tone}
Story brief: {brief_snippet}
Characters: {cast_snippet}
{context_section}

Write the next 2-3 paragraphs, maintaining continuity and quality.
Match the style and voice of the previous section."""

    response = await llm.ainvoke(prompt)
    return response.content


@tool
async def create_dialogue(
    character_a: str,
    character_b: str,
    topic: str,
    mood: str,
    lore_context: list[Any] | None = None,
) -> str:
    """Create dialogue between two characters.

    Args:
        character_a: First character description
        character_b: Second character description
        topic: What they're discussing
        mood: tense/friendly/mysterious/confrontational

    Returns:
        Dialogue exchange (6-10 lines)
    """
    llm = get_chat_model(task="creative", temperature=0.9, streaming=False)

    context_section = ""
    if lore_context:
        normalized = [
            _normalize_context_entry(block) for block in lore_context if block is not None
        ]
        joined_context = "\n".join(entry.strip() for entry in normalized if entry and entry.strip())
        if joined_context:
            context_section = f"\nRelevant Lore:\n{joined_context[:1000]}\n"

    prompt = f"""Write dialogue for LuminariMUD.

Character A: {character_a}
Character B: {character_b}
Topic: {topic}
Mood: {mood}
{context_section}

Write 6-10 lines of natural dialogue that:
- Reveals character personalities
- Advances the topic
- Maintains the specified mood
- Feels authentic to the fantasy setting

Format as:
Character Name: "Dialogue"
Include brief action tags where appropriate."""

    response = await llm.ainvoke(prompt)
    return response.content


@tool
async def combine_quest_phases(
    quest_title: str,
    phase_count: int = 3,
    phase_summaries: str | None = None,
    quest_hook: str | None = None,
    original_request: str | None = None,
) -> str:
    """Combine quest phases into a complete narrative with proper conclusion.

    WHEN TO USE: After creating 3+ quest phases, BEFORE rewards.

    Args:
        quest_title: Title for the complete quest
        phase_count: Number of phases created (usually 3-5)
        phase_summaries: Optional summary of created phases
        quest_hook: Optional quest hook that started the quest
        original_request: Optional original user request for context

    Returns:
        Narrative summary tying all phases together with conclusion
    """
    llm = get_chat_model(task="chat", temperature=0.7, streaming=False)

    context = ""
    if original_request:
        context += f"\nOriginal Request: {original_request}\n"
    if quest_hook:
        context += f"\nQuest Hook: {quest_hook}\n"
    if phase_summaries:
        context += f"\nPhase Content:\n{phase_summaries}\n"

    prompt = f"""You are combining {phase_count} quest phases into a complete narrative.

Quest Title: {quest_title}
{context}

Based on the phases that were created, write a brief narrative summary that:
1. Explains how the phases connect and flow together
2. Describes the overall story arc from beginning to climax
3. Provides a satisfying CONCLUSION that resolves the main conflict
4. Notes any intentional loose threads for future quests (if any)
5. Emphasizes the transformation/growth of the player through the quest
6. MAINTAINS CONSISTENCY with the character names, locations, and details from the phases

Write 2-3 paragraphs that tie everything together into a cohesive story."""

    response = await llm.ainvoke(prompt)
    return response.content


@tool
async def validate_lore_consistency(content: str, lore_context: list[str]) -> dict[str, Any]:
    """Check if created content is consistent with established lore.

    Args:
        content: The generated content to check
        lore_context: Relevant lore to check against

    Returns:
        Dict with is_consistent and any issues found
    """
    llm = get_chat_model(task="reasoning", temperature=0, streaming=False)

    context_text = (
        "\n".join(f"[Block {idx}] {block}" for idx, block in enumerate(lore_context[:5]))
        if lore_context
        else "No context"
    )

    prompt = f"""Check this content for consistency with Luminari lore.

Content to check:
{content[:1000]}

Established lore:
{context_text}

Identify any contradictions or inconsistencies.

Output as JSON:
{{"is_consistent": true/false, "issues": ["list of issues if any"]}}"""

    response = await llm.ainvoke(prompt)
    try:
        return json.loads(response.content)
    except Exception:
        return {"is_consistent": True, "issues": []}


@tool
async def get_entity_details(entity_name: str) -> str:
    """Get complete information about a specific entity from Neo4j knowledge graph.

    WHEN TO USE: After search_lore finds an entity name, use this to get ALL details about that entity.

    Args:
        entity_name: Exact name of the entity (from search_lore results)

    Returns:
        Formatted string with entity details and relationships
    """
    import os

    from neo4j import AsyncGraphDatabase

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        async with driver.session() as session:
            # Direct Neo4j query to get EVERYTHING about the entity
            result = await session.run(
                """
                // Find the entity (case-insensitive partial match)
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($entity_name)
                WITH e
                ORDER BY size(e.name)  // Prefer shorter names (likely exact matches)
                LIMIT 1

                // Get all outgoing relationships
                OPTIONAL MATCH (e)-[r_out]->(target:Entity)
                WITH e,
                     collect(DISTINCT {
                         type: type(r_out),
                         target: target.name,
                         target_type: labels(target)[0],
                         fact: r_out.fact,
                         created_at: r_out.created_at,
                         properties: properties(r_out)
                     }) as outgoing

                // Get all incoming relationships
                OPTIONAL MATCH (source:Entity)-[r_in]->(e)
                WITH e, outgoing,
                     collect(DISTINCT {
                         type: type(r_in),
                         source: source.name,
                         source_type: labels(source)[0],
                         fact: r_in.fact,
                         created_at: r_in.created_at,
                         properties: properties(r_in)
                     }) as incoming

                // Return everything
                RETURN e as entity,
                       labels(e) as labels,
                       properties(e) as properties,
                       outgoing,
                       incoming,
                       size(outgoing) + size(incoming) as total_relationships
            """,
                {"entity_name": entity_name},
            )

            record = await result.single()

            if record and record["entity"]:
                # Process the entity data - convert datetime objects to strings
                entity_props = {}
                for k, v in dict(record["properties"]).items():
                    entity_props[k] = str(v) if hasattr(v, "isoformat") else v
                entity_labels = record["labels"]

                # Process relationships to extract Graphiti custom edge data
                relationships = []

                # Add outgoing relationships
                for rel in record["outgoing"]:
                    if rel.get("target"):  # Filter null relationships
                        # Convert any datetime objects to strings and skip embeddings
                        custom_props = {}
                        for k, v in rel.get("properties", {}).items():
                            if k not in [
                                "fact",
                                "created_at",
                                "uuid",
                                "group_id",
                                "fact_embedding",
                                "name_embedding",
                            ]:
                                # Skip embedding fields and convert datetime to string
                                if not k.endswith("_embedding"):
                                    custom_props[k] = str(v) if hasattr(v, "isoformat") else v

                        relationships.append(
                            {
                                "direction": "outgoing",
                                "type": rel["type"],
                                "target": rel["target"],
                                "target_type": rel.get("target_type", "Entity"),
                                "fact": rel.get("fact", ""),
                                "created_at": (
                                    str(rel.get("created_at", "")) if rel.get("created_at") else ""
                                ),
                                "custom_properties": custom_props,
                            }
                        )

                # Add incoming relationships
                for rel in record["incoming"]:
                    if rel.get("source"):  # Filter null relationships
                        # Convert any datetime objects to strings and skip embeddings
                        custom_props = {}
                        for k, v in rel.get("properties", {}).items():
                            if k not in [
                                "fact",
                                "created_at",
                                "uuid",
                                "group_id",
                                "fact_embedding",
                                "name_embedding",
                            ]:
                                # Skip embedding fields and convert datetime to string
                                if not k.endswith("_embedding"):
                                    custom_props[k] = str(v) if hasattr(v, "isoformat") else v

                        relationships.append(
                            {
                                "direction": "incoming",
                                "type": rel["type"],
                                "source": rel["source"],
                                "source_type": rel.get("source_type", "Entity"),
                                "fact": rel.get("fact", ""),
                                "created_at": (
                                    str(rel.get("created_at", "")) if rel.get("created_at") else ""
                                ),
                                "custom_properties": custom_props,
                            }
                        )

                # Limit relationships to prevent huge responses
                MAX_RELATIONSHIPS = 20
                if len(relationships) > MAX_RELATIONSHIPS:
                    # Take a sample of important relationships
                    relationships = relationships[:MAX_RELATIONSHIPS]

                # Format as a readable string for the agent
                entity_name = entity_props.get("name", entity_name)
                entity_type = entity_labels[0] if entity_labels else "Entity"
                summary = entity_props.get("summary", "No summary available")

                result = f"# Entity: {entity_name}\n"
                result += f"Type: {entity_type}\n"
                result += f"Summary: {summary}\n\n"
                result += f"## Relationships ({len(relationships)} shown of {record['total_relationships']} total)\n\n"

                # Group relationships by type
                by_type = {}
                for rel in relationships:
                    rel_type = rel["type"]
                    if rel_type not in by_type:
                        by_type[rel_type] = []
                    by_type[rel_type].append(rel)

                for rel_type, rels in by_type.items():
                    result += f"### {rel_type} ({len(rels)})\n"
                    for rel in rels[:5]:  # Show max 5 per type
                        if rel.get("direction") == "outgoing":
                            result += f"- → {rel.get('target', 'Unknown')}"
                        else:
                            result += f"- ← {rel.get('source', 'Unknown')}"

                        if rel.get("fact"):
                            result += f": {rel['fact'][:100]}"
                        result += "\n"
                    if len(rels) > 5:
                        result += f"- ... and {len(rels) - 5} more\n"
                    result += "\n"

                return result
            else:
                return f"No entity found matching '{entity_name}'. Try search_lore first to find exact entity names."

    except Exception as e:
        logger.error("Failed to get entity details from Neo4j (%s)", type(e).__name__)
        return public_error_message("Entity lookup")
    finally:
        await driver.close()


@tool
async def explore_relationships(
    source_entity: str, relationship_type: str | None = None, max_hops: int = 2
) -> dict[str, Any]:
    """Explore relationships between entities in the knowledge graph.

    WHEN TO USE: To understand connections between entities or trace relationship paths.

    Args:
        source_entity: Starting entity name
        relationship_type: Optional specific relationship type to follow (e.g., "created_by", "allied_with")
        max_hops: Maximum relationship distance to explore (1-3)

    Returns:
        Dict with relationship paths and connected entities
    """
    import os

    import httpx

    url = os.getenv("LANGCHAIN_INTERNAL_API_BASE", "http://localhost:8003").rstrip("/")
    headers = {}
    api_key = os.getenv("SAGE_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    # Build query focusing on relationships
    if relationship_type:
        query = f'"{source_entity}" {relationship_type} connections relationships'
    else:
        query = f'"{source_entity}" all connections relationships network'

    payload = {
        "query": query,
        "limit": 15,  # More results for relationship exploration
        "include_entities": True,
        "threshold": 0.2,  # Lower threshold for broader exploration
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{url}/api/v1/rag/query", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Build relationship graph
            paths = []
            visited_entities = set()

            # First hop - direct relationships
            for rel in data.get("relationships", []):
                if rel.get("source_name", "").lower() == source_entity.lower():
                    if not relationship_type or rel.get("type", "") == relationship_type:
                        paths.append(
                            {
                                "path": [source_entity, rel.get("target_name", "")],
                                "relationship": rel.get("type", ""),
                                "fact": (
                                    rel.get("metadata", {}).get("fact", "")
                                    if rel.get("metadata")
                                    else ""
                                ),
                                "properties": rel.get("metadata", {}),
                                "hops": 1,
                            }
                        )
                        visited_entities.add(rel.get("target_name", ""))

            # Second hop if requested
            if max_hops >= 2 and visited_entities:
                for rel in data.get("relationships", []):
                    if rel.get("source_name", "") in visited_entities:
                        paths.append(
                            {
                                "path": [
                                    source_entity,
                                    rel.get("source_name", ""),
                                    rel.get("target_name", ""),
                                ],
                                "relationship": rel.get("type", ""),
                                "fact": (
                                    rel.get("metadata", {}).get("fact", "")
                                    if rel.get("metadata")
                                    else ""
                                ),
                                "properties": rel.get("metadata", {}),
                                "hops": 2,
                            }
                        )

            return {
                "source": source_entity,
                "paths": paths[:20],  # Limit to 20 paths
                "connected_entities": list(visited_entities),
                "relationship_types": list({p["relationship"] for p in paths}),
                "metadata": {
                    "total_paths": len(paths),
                    "max_hops": max_hops,
                    "filter": relationship_type,
                },
            }
    except Exception as e:
        logger.error("Failed to explore relationships (%s)", type(e).__name__)
        return {
            "source": source_entity,
            "paths": [],
            "error": public_error_message("Relationship exploration"),
        }


@tool
async def verify_facts(statement: str, entities_mentioned: list[str]) -> dict[str, Any]:
    """Verify if a statement aligns with the knowledge graph facts.

    WHEN TO USE: To fact-check content against established lore.

    Args:
        statement: The statement to verify
        entities_mentioned: List of entity names mentioned in the statement

    Returns:
        Dict with verification result and supporting/conflicting evidence
    """
    import os

    import httpx

    # Gather facts about mentioned entities
    url = os.getenv("LANGCHAIN_INTERNAL_API_BASE", "http://localhost:8003").rstrip("/")
    headers = {}
    api_key = os.getenv("SAGE_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    all_facts = []

    async with httpx.AsyncClient(timeout=30) as client:
        for entity in entities_mentioned[:5]:  # Limit to 5 entities
            payload = {
                "query": f'"{entity}" facts properties details',
                "limit": 5,
                "include_entities": True,
                "threshold": 0.3,
            }

            try:
                response = await client.post(
                    f"{url}/api/v1/rag/query", json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()

                # Collect facts from relationships
                for rel in data.get("relationships", []):
                    if rel.get("metadata", {}).get("fact"):
                        all_facts.append(
                            {
                                "entity": entity,
                                "fact": rel["metadata"]["fact"],
                                "relationship": rel.get("type", ""),
                                "target": rel.get("target_name", ""),
                            }
                        )

                # Collect chunks as context
                for chunk in data.get("chunks", [])[:2]:
                    if chunk.get("text"):
                        all_facts.append(
                            {"entity": entity, "fact": chunk["text"][:500], "type": "context"}
                        )

            except Exception as e:
                logger.warning("Failed to get entity facts (%s)", type(e).__name__)

    # Use LLM to verify the statement against collected facts
    llm = get_chat_model(task="reasoning", temperature=0, streaming=False)

    facts_text = "\n".join(
        [
            f"- {f.get('entity', 'General')}: {f.get('fact', '')}"
            for f in all_facts[:15]  # Limit to 15 facts
        ]
    )

    prompt = f"""Verify this statement against the established facts:

Statement to verify:
"{statement}"

Established facts from the knowledge graph:
{facts_text or "No specific facts found for mentioned entities."}

Analyze whether the statement is:
1. SUPPORTED - Aligns with established facts
2. CONTRADICTED - Conflicts with established facts
3. UNVERIFIABLE - No relevant facts found
4. PARTIALLY_SUPPORTED - Some parts align, others don't

Output as JSON:
{{"verdict": "SUPPORTED/CONTRADICTED/UNVERIFIABLE/PARTIALLY_SUPPORTED", "explanation": "...", "supporting_facts": [...], "conflicting_facts": [...]}}"""

    response = await llm.ainvoke(prompt)

    try:
        import json

        result = json.loads(response.content)
        result["statement"] = statement
        result["entities_checked"] = entities_mentioned
        result["facts_reviewed"] = len(all_facts)
        return result
    except Exception:
        return {
            "statement": statement,
            "verdict": "UNVERIFIABLE",
            "explanation": "Could not parse verification result",
            "entities_checked": entities_mentioned,
            "facts_reviewed": len(all_facts),
        }


@tool
async def create_complete_quest(
    requirements: str, lore_context: list[Any] | None = None, use_lore_context: bool = True
) -> dict[str, Any]:
    """Create a COMPLETE quest with proper narrative flow and context preservation.

    WHEN TO USE: When user asks for a full quest (not just a hook or single phase).
    This creates a complete multi-phase quest with:
    - Quest hook
    - 3-5 interconnected phases
    - Resolution
    - Rewards

    The workflow ensures:
    - Narrative continuity between phases
    - Character names remain consistent
    - Story follows user's requirements exactly
    - Each phase builds on the previous one
    - THE PLAYER is always the protagonist

    Args:
        requirements: The user's quest requirements/description
        lore_context: Optional list of lore context from previous searches
        use_lore_context: Whether to search for relevant lore (if not provided)

    Returns:
        Complete quest with all phases, resolution, and rewards
    """
    from .quest_workflow import QuestWorkflow

    # Use provided lore context or search for it
    quest_lore_context: list[str] = []
    if lore_context:
        # Use the provided context from the agent's searches
        quest_lore_context = [
            entry.strip()
            for entry in (
                _normalize_context_entry(block) for block in lore_context if block is not None
            )
            if entry and entry.strip()
        ]
        logger.info(f"Using provided lore context: {len(quest_lore_context)} items")
    elif use_lore_context:
        # Extract key terms from requirements for search
        search_terms = []
        if "wizard" in requirements.lower():
            search_terms.append("wizard mage arcane")
        if "crystal" in requirements.lower() or "arcanite" in requirements.lower():
            search_terms.append("crystalline arcanite crystal magic")
        if "ruin" in requirements.lower():
            search_terms.append("ruins ancient sites")

        if search_terms:
            try:
                from .chains.retrieval import RetrievalChain

                retrieval = RetrievalChain()
                for term in search_terms[:2]:  # Limit searches
                    result = await retrieval.ainvoke({"query": term})
                    if result.get("context_blocks"):
                        quest_lore_context.extend(result["context_blocks"][:2])
            except Exception as e:
                logger.warning("Could not get lore context (%s)", type(e).__name__)

    # Create quest with workflow
    workflow = QuestWorkflow()
    complete_quest = await workflow.build_quest(requirements, quest_lore_context)

    return complete_quest


@tool
async def create_story(
    requirements: str,
    length: str = "medium",
    include_metadata: bool = True,
    lore_context: list[Any] | None = None,
) -> dict[str, Any]:
    """Create a structured, multi-section story for the Luminari universe.

    Args:
        requirements: Narrative requirements or prompt from the user
        length: Desired length "short", "medium", or "epic"
        include_metadata: Whether to include structured metadata in the result
        lore_context: Optional lore context blocks to ground the story

    Returns:
        Dict with title, synopsis, sections, characters, and full story text
    """

    normalized_context: list[str] = []
    if lore_context:
        normalized_context = [
            entry.strip()
            for entry in (
                _normalize_context_entry(block) for block in lore_context if block is not None
            )
            if entry and entry.strip()
        ]

    workflow = StoryWorkflow()
    story = await workflow.build_story(requirements, normalized_context, story_length=length)

    if include_metadata:
        return story

    return {
        "title": story.get("title"),
        "story": story.get("full_story"),
    }


def get_focused_tools():
    """Get all focused tools for the ReAct agent."""
    return [
        search_lore,
        answer_lore_question,
        create_complete_quest,  # New workflow-based quest creator
        create_quest_hook,
        create_quest_phase,
        create_quest_reward,
        create_npc,
        create_location_description,
        create_story,
        create_story_opening,
        continue_story,
        create_dialogue,
        combine_quest_phases,
        validate_lore_consistency,
        get_entity_details,
        explore_relationships,
        verify_facts,
    ]
