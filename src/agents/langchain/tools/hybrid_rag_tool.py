"""Hybrid Graph RAG LangChain Tool.

Wraps existing internal REST endpoint /api/v1/rag/query to provide
retrieval context to LangChain chains. Keeps legacy implementation
untouched.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from pydantic import Field


class HybridGraphRAGTool(BaseTool):
    name: str = "hybrid_graph_rag"
    description: str = (
        "Retrieve hybrid semantic + graph context for a lore query. "
        "Input should be a natural language string. Returns JSON with: "
        "entities, relationships, chunks, provenance."
    )

    endpoint: str = Field(default="/api/v1/rag/query")
    base_url: str = Field(
        default_factory=lambda: os.getenv("LANGCHAIN_INTERNAL_API_BASE", "http://localhost:8003")
    )
    timeout: int = Field(default=30)

    def _run(self, query: str, run_manager: Any | None = None) -> str:  # type: ignore[override]
        return self._invoke(query)

    async def _arun(self, query: str, run_manager: Any | None = None) -> str:  # type: ignore[override]
        return await self._ainvoke(query)

    def _invoke(self, query: str) -> str:
        payload = {"query": query, "limit": 12, "include_entities": True, "threshold": 0.05}
        url = self.base_url.rstrip("/") + self.endpoint
        headers = {}
        api_key = os.getenv("SAGE_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key
        try:
            r = httpx.post(url, json=payload, timeout=self.timeout, headers=headers)
            r.raise_for_status()
            return r.text
        except Exception:
            return '{"error":"rag_failed"}'

    async def _ainvoke(self, query: str) -> str:
        payload = {"query": query, "limit": 12, "include_entities": True, "threshold": 0.05}
        url = self.base_url.rstrip("/") + self.endpoint
        headers = {}
        api_key = os.getenv("SAGE_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            try:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                return r.text
            except Exception:
                return '{"error":"rag_failed"}'
