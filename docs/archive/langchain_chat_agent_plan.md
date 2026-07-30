# LangChain Chat Agent Plan (Parallel Implementation)

Purpose: Introduce a LangChain-based chat / quest / narrative agent alongside existing PydanticAI chat agent with instant fallback.

## Scope
In-scope:
- New /api/v2/chat (or /api/v1/chat/message?engine=langchain) endpoints
- Router (classifier) → Q&A | Quest Planning | Narrative Generation | Meta Help
- Hybrid Graph RAG tool wrapper (calls existing /api/v1/rag/query internally)
- Streaming via current SSE pattern
- Observability: chain route, tool invocations, token counts, latency
- Config + per-request fallback to legacy

Out-of-scope (for this week):
- Replacing ingestion / validation agents
- Persistent long-term memory beyond rolling window
- Advanced re-ranking or multi-hop planning chains

## Chains
1. ClassifierChain → route {lore_query, quest_planning, narrative_generation, meta_help}
2. RetrievalSubChain → wraps tool call and context condensation
3. DirectAnswerChain → factual grounded answer
4. QuestPlannerChain → objective, premise, phases[], unresolved threads
5. NarrativeChain → outline (beats) + optional expansion

## Tool: hybrid_graph_rag
Input: { query: str, mode?: str }
Output: {
  query_used, entities[], relationships[], episodes[], raw_chunks[], provenance{vector_hits, graph_nodes}
}

## Fallback Strategy
- ENV: CHAT_ENGINE=legacy|langchain (default legacy)
- Header: X-Chat-Engine overrides
- On chain failure → log + automatic legacy dispatch

## Transparency
- Each response attaches debug block if ?trace=1: { route, tool_calls, context_tokens, latency_ms }
  (Hidden in normal responses.)

## Success Metrics (Demo)
- Lore answer < 6s
- Quest plan clearly phased + real entities
- Narrative uses canonical anchors; embellishments labeled
- Toggle demo (legacy ↔ langchain) live

## Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Misclassification | Wrong chain | Conservative classifier prompts + fallback to lore_query |
| Hallucinated lore | Credibility | Retrieval grounding + "Insufficient canonical context" guard |
| JSON schema drift | Break client | Retry parser (2 attempts) + minimal schema |
| Latency spikes | Demo failure | Cap retrieval results; single pass; async streaming |

## Week Timeline (Compressed)
Day 1: Classifier prompt + tool wrapper + skeleton modules
Day 2: DirectAnswerChain + streaming integration + config toggle
Day 3: QuestPlannerChain JSON + evaluation examples
Day 4: NarrativeChain + embellishment tagging + trace logging
Day 5: Hardening (retry, guard phrases) + latency tuning
Day 6: Demo script + polish + rollback test

## Open Questions
- Use distinct endpoint path or query param? (Default: query param engine=langchain)
- Model choice unified? (Initial: same model as legacy for fairness)

## Next Implementation Steps
1. Add langchain dependencies (langchain-core, langchain-openai, langchain-community)
2. Create `src/agents/langchain/` package with:
   - tool_hybrid_rag.py
   - classifier.py
   - chains/retrieval.py, chains/direct_answer.py, chains/quest_planner.py, chains/narrative.py
   - router.py
   - service.py (orchestrator for FastAPI endpoint)
3. Add config + toggle util
4. Add new FastAPI endpoint wrapper (no change to legacy endpoint)
5. Add minimal tests for classifier + quest json schema

---
This document will be updated as implementation progresses.
