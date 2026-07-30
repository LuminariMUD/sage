"""Retrieval sub-chain: invoke hybrid RAG tool and prepare condensed context."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import Runnable

from ..tools.hybrid_rag_tool import HybridGraphRAGTool


class RetrievalChain(Runnable):
    """Lightweight runnable for retrieval + condensation.

    Input: {"query": str}
    Output: {"query": str, "context_blocks": List[str], "raw": Dict}
    """

    def __init__(self, tool: HybridGraphRAGTool | None = None):
        self.tool = tool or HybridGraphRAGTool()

    def invoke(self, input: dict[str, Any], config: dict | None = None) -> dict[str, Any]:  # type: ignore[override]
        query = input.get("query", "").strip()
        raw_json = self.tool._invoke(query)
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError:
            raw = {"error": "decode_failed"}
        blocks: list[str] = []
        if isinstance(raw, dict):
            for chunk in raw.get("chunks", [])[:20]:
                txt = chunk.get("text") if isinstance(chunk, dict) else None
                if txt:
                    blocks.append(txt.strip())
            graph_metadata = (
                raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
            )
            for ent in (graph_metadata.get("graph_entities") or [])[:10]:
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
                    details = ", ".join(filter(None, [desc.strip(), attr_text.strip()]))
                    if name and details:
                        blocks.append(f"GRAPH ENTITY {name} ({etype}): {details}")
            for rel in (graph_metadata.get("graph_relationships") or [])[:15]:
                if isinstance(rel, dict):
                    r_type = rel.get("type", "related_to")
                    source = rel.get("source", "?")
                    target = rel.get("target", "?")
                    metadata = (
                        rel.get("metadata", {}) if isinstance(rel.get("metadata"), dict) else {}
                    )
                    fact = metadata.get("fact") or rel.get("fact", "")
                    attr = (
                        metadata.get("attributes", {})
                        if isinstance(metadata.get("attributes"), dict)
                        else {}
                    )
                    attr_text = "; ".join(
                        f"{k.replace('_', ' ').title()}: {v}"
                        for k, v in attr.items()
                        if v not in (None, "", [])
                    )
                    insight_parts = [part for part in [fact, attr_text] if part]
                    if insight_parts:
                        blocks.append(
                            f"GRAPH RELATIONSHIP {r_type} ({source} -> {target}): {'; '.join(insight_parts)}"
                        )
        return {"query": query, "context_blocks": blocks, "raw": raw}

    async def ainvoke(self, input: dict[str, Any], config: dict | None = None) -> dict[str, Any]:  # type: ignore[override]
        query = input.get("query", "").strip()
        raw_json = await self.tool._ainvoke(query)
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError:
            raw = {"error": "decode_failed"}
        blocks: list[str] = []
        if isinstance(raw, dict):
            for chunk in raw.get("chunks", [])[:20]:
                txt = chunk.get("text") if isinstance(chunk, dict) else None
                if txt:
                    blocks.append(txt.strip())
            graph_metadata = (
                raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
            )
            for ent in (graph_metadata.get("graph_entities") or [])[:10]:
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
                    details = ", ".join(filter(None, [desc.strip(), attr_text.strip()]))
                    if name and details:
                        blocks.append(f"GRAPH ENTITY {name} ({etype}): {details}")
            for rel in (graph_metadata.get("graph_relationships") or [])[:15]:
                if isinstance(rel, dict):
                    r_type = rel.get("type", "related_to")
                    source = rel.get("source", "?")
                    target = rel.get("target", "?")
                    metadata = (
                        rel.get("metadata", {}) if isinstance(rel.get("metadata"), dict) else {}
                    )
                    fact = metadata.get("fact") or rel.get("fact", "")
                    attr = (
                        metadata.get("attributes", {})
                        if isinstance(metadata.get("attributes"), dict)
                        else {}
                    )
                    attr_text = "; ".join(
                        f"{k.replace('_', ' ').title()}: {v}"
                        for k, v in attr.items()
                        if v not in (None, "", [])
                    )
                    insight_parts = [part for part in [fact, attr_text] if part]
                    if insight_parts:
                        blocks.append(
                            f"GRAPH RELATIONSHIP {r_type} ({source} -> {target}): {'; '.join(insight_parts)}"
                        )
        return {"query": query, "context_blocks": blocks, "raw": raw}
