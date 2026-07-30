LangChain Chat Agent TODO (Week Sprint)

Legend: [ ] pending  [~] in progress  [x] done

Phase 1 – Foundations
[ ] Add dependencies: langchain-core, langchain-openai, langchain-community, langchain-text-splitters (defer until code integration)
[ ] Create package skeleton under src/agents/langchain/
[ ] Implement hybrid_graph_rag tool wrapper (calls internal RAG endpoint)
[ ] Draft classifier prompt + implement simple rule/LLM hybrid

Phase 2 – Core Chains
[ ] RetrievalSubChain (tool invoke + condensation)
[ ] DirectAnswerChain with grounding & insufficiency guard
[ ] Streaming integration using callbacks

Phase 3 – Quest & Narrative
[ ] QuestPlannerChain (objective, premise, phases[], unresolved_threads)
[ ] NarrativeChain (outline + beat expansion, embellishment tagging)

Phase 4 – Routing & API
[ ] Router that selects chain and logs route decision
[ ] FastAPI endpoint (/api/v1/chat/message?engine=langchain) integrating storage
[ ] Fallback to legacy on exception or disabled flag

Phase 5 – Observability & Hardening
[ ] Trace / debug mode (?trace=1) returns route + timings
[ ] Retry wrapper for JSON parsing (max 2)
[ ] Token + latency metrics logging

Phase 6 – Testing & Demo Prep
[ ] Unit tests: classifier, quest output schema, narrative outline
[ ] Latency smoke script
[ ] Demo scenario script (sample prompts)
[ ] Rollback toggle verification

Stretch (If Time)
[ ] Simple rerank of retrieved chunks by semantic similarity
[ ] Reusable prompt templates externalized

Notes:
- Keep legacy untouched.
- Avoid deep dependency lock conflicts—pin minimal versions.
