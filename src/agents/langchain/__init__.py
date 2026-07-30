"""LangChain chat agent package (parallel to legacy PydanticAI chat agent).

Provides:
- Tool wrappers (hybrid Graph RAG)
- Classifier / router
- Chains: retrieval, direct answer, quest planner, narrative
- Service orchestrator for FastAPI endpoint integration

This module is intentionally minimal at initialization time to avoid
import-time overhead unless LangChain engine is selected.
"""
