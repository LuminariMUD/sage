"""Grounded lore answer chain optimized for comprehensive responses.

This module replaces the older reflection-heavy implementation with a
deterministic two-stage pipeline:

1. Digest canonical context into structured bullet points that enumerate the
   facts available to answer the user's question.
2. Compose a final response that cites the context blocks explicitly and
   surfaces every useful detail, prioritising completeness over brevity.

When an OpenAI API key is unavailable the chain falls back to a deterministic
response builder so tests remain offline-friendly.
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.config import text_profile_is_ready
from src.llm.langchain_helpers import get_chat_model

logger = logging.getLogger(__name__)


def _normalize_context_blocks(blocks: list[Any]) -> list[str]:
    """Normalise varied context payloads into unique text snippets."""

    normalised: list[str] = []
    seen: set[str] = set()

    for block in blocks:
        text: str | None = None
        if isinstance(block, str):
            text = block
        elif isinstance(block, dict):
            for key in ("text", "content", "chunk", "summary", "body"):
                value = block.get(key)
                if isinstance(value, str) and value.strip():
                    text = value
                    break
        if not text:
            continue
        trimmed = text.strip()
        if not trimmed:
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        normalised.append(trimmed)

    return normalised


def _format_context_blocks(blocks: list[str]) -> str:
    """Render blocks with explicit numbering for prompt clarity."""

    if not blocks:
        return "<no context retrieved>"
    return "\n".join(f"[Block {idx}] {text}" for idx, text in enumerate(blocks, 1))


def _shorten(text: str, width: int = 220) -> str:
    """Deterministically shorten text for previews and sources."""

    return textwrap.shorten(text.replace("\n", " "), width=width, placeholder="…")


class _FallbackChunk:
    def __init__(self, content: str):
        self.content = content


class _FallbackChatModel:
    """Minimal stand-in used when the selected text profile is not ready."""

    def __init__(self, label: str = "fallback"):
        self.label = label

    def invoke(self, messages):  # type: ignore[override]
        # Compose a deterministic placeholder using the final user message.
        last_message = messages[-1]
        if isinstance(last_message, dict):
            content = last_message.get("content", "")
        else:
            content = getattr(last_message, "content", "")
        return _FallbackChunk(
            f"(Text provider unavailable) Unable to call model '{self.label}'. "
            f"Returning placeholder content based on provided input.\n\n{content}"
        )

    def stream(self, messages):  # pragma: no cover - unused in tests
        yield from ()


DIGEST_SYSTEM_PROMPT = """You are an archivist distilling canonical knowledge of Lumia.

Context blocks arrive in three flavours:
- Plain prose passages: these quote the canonical episode text and are the
  highest-authority sources.
- Lines prefixed with ENTITY ...: these are curated entity summaries extracted
  from the graph and reflect canon-fast facts about the entity.
- Lines prefixed with GRAPH ENTITY/GRAPH RELATIONSHIP: these are supporting
  notes derived from the knowledge graph and may lag behind canon.

Always ground direct conclusions in the prose passages first. Use entity
summaries to reinforce or extend the prose when it is sparse. Use graph
information only to corroborate or extend what the prose or entity summary
establishes. If graph details contradict the prose or entity summary, trust the
canon sources and record the disagreement under "gaps".

Analyse the numbered context blocks and produce a structured JSON object with
these keys:
  - "direct_answers": list of objects describing statements that answer the
    question directly. Each object must have "summary" (string) and "blocks"
    (list of integers referencing block numbers).
  - "supporting_facts": list of additional facts that expand on the topic.
  - "related_details": optional facts that may be tangentially helpful.
  - "gaps": points the archives do not cover but the user might expect.

Return ONLY JSON. Do not include prose outside of the JSON object."""


FINAL_SYSTEM_PROMPT = """You are the Luminari Sage, guardian of Lumia's archives.

Compose thorough, in-universe responses that maximise useful detail while
remaining faithful to the supplied context. Treat the prose passages (plain
context blocks) as canonical truth. Treat entity summaries (lines beginning with
"ENTITY ") as canon-supporting references that should be incorporated whenever
they add descriptive clarity. Graph-derived blocks (prefixed with GRAPH) are
secondary; weave them in only when they align with the prose/entity summaries,
and if any contradiction appears, note it explicitly while siding with the
canon sources. Minor inconsistencies are acceptable when they can be traced back
to the episode text or the entity summary.

Requirements:
1. Begin with "## Direct Answer" summarising the core response.
2. Follow with "## Canonical Details" covering every supporting fact.
3. Include "## Key Entities & Roles" and "## Notable Connections" when the
   digest lists any.
4. When context contains lines beginning with "GRAPH RELATIONSHIP", add a
   "## Key Connections" section that weaves the most relevant relationships into
   the narrative and cross-checks them against the prose.
5. Provide "## Additional Insights" for related_details.
6. Reference context blocks inline as [Block X] for every factual statement.
7. Conclude with "## Source Blocks" enumerating each block with a short
   preview so readers can trace the origin of the information.
8. When the digest notes gaps, acknowledge them explicitly.

Stay immersed in-world; never mention prompts, APIs, or tooling."""


DIGEST_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", DIGEST_SYSTEM_PROMPT),
        ("human", "Question: {question}\n\nContext Blocks:\n{context}\n\nReturn JSON digest:"),
    ]
)


FINAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", FINAL_SYSTEM_PROMPT),
        (
            "human",
            """Question: {question}\n\nContext Blocks:\n{context}\n\n"""
            "Structured Digest:\n{digest}\n\n"
            "{history_instructions}"
            "Write the complete answer now.",
        ),
    ]
)


def _empty_digest() -> dict[str, Any]:
    return {
        "direct_answers": [],
        "supporting_facts": [],
        "related_details": [],
        "gaps": [],
    }


def _ensure_json(text: str) -> dict[str, Any]:
    """Robustly parse JSON produced by the LLM."""

    text = text.strip()
    if not text:
        return _empty_digest()
    # Attempt direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to locate the first JSON object within the text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            logger.debug("Failed to parse JSON snippet from digest output")

    logger.debug("Digest output was not valid JSON; returning empty digest")
    return _empty_digest()


class DirectAnswerChain(Runnable):
    """Produce comprehensive lore answers grounded in retrieved context."""

    def __init__(
        self,
        model_name: str = "gpt-4.1",
        temperature: float = 0.0,
        enable_reflection: bool = False,  # Kept for API compatibility; ignored.
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature

        use_real_llm = text_profile_is_ready("reasoning")

        if use_real_llm:
            try:
                # Use provider abstraction for answer model
                # Use "reasoning" task for factual answers
                self.answer_llm = get_chat_model(
                    task="reasoning",
                    temperature=temperature,
                    streaming=False,
                    max_tokens=3000,
                )
            except Exception as exc:  # pragma: no cover - network failures
                logger.warning(
                    "Falling back to deterministic answer model (%s)",
                    type(exc).__name__,
                )
                self.answer_llm = _FallbackChatModel(model_name)
        else:
            self.answer_llm = _FallbackChatModel(model_name)

        # Digest model uses a smaller temperature for structured output
        if use_real_llm:
            try:
                # For digest, use extraction task (lower temperature, structured output)
                self.digest_llm = get_chat_model(
                    task="extraction",
                    temperature=0.0,
                    streaming=False,
                    max_tokens=2000,
                )
            except Exception as exc:  # pragma: no cover - network failures
                logger.warning(
                    "Falling back to deterministic digest model (%s)",
                    type(exc).__name__,
                )
                self.digest_llm = _FallbackChatModel("digest")
        else:
            self.digest_llm = _FallbackChatModel("digest")

        # Compatibility attribute retained for older call sites
        self.retrieval_tool: Any | None = None

    # ------------------------------------------------------------------
    # Digest helpers
    # ------------------------------------------------------------------
    def _fallback_digest(self, blocks: list[str]) -> dict[str, Any]:
        digest = _empty_digest()
        for idx, text in enumerate(blocks, 1):
            summary = _shorten(text, width=200)
            entry = {"summary": summary, "blocks": [idx]}
            if text.strip().upper().startswith("GRAPH "):
                digest["supporting_facts"].append(entry)
            else:
                digest["direct_answers"].append(entry)
        return digest

    def _build_digest(self, question: str, blocks: list[str]) -> dict[str, Any]:
        if not blocks:
            return _empty_digest()

        if isinstance(self.digest_llm, _FallbackChatModel):
            return self._fallback_digest(blocks)

        prompt = DIGEST_PROMPT.format_prompt(
            question=question,
            context=_format_context_blocks(blocks),
        )
        response = self.digest_llm.invoke(prompt.to_messages())
        digest = _ensure_json(response.content)
        if not isinstance(digest, dict):
            logger.debug("Digest response was not a dict; using fallback")
            digest = self._fallback_digest(blocks)
        return digest

    def _digest_to_text(self, digest: dict[str, Any]) -> str:
        if not digest:
            return "(no digest)"

        lines: list[str] = []

        def _render(key: str, heading: str) -> None:
            items = digest.get(key, [])
            if not items:
                return
            lines.append(f"{heading}:")
            for item in items:
                if not isinstance(item, dict):
                    continue
                summary = item.get("summary") or item.get("detail") or str(item)
                blocks = item.get("blocks") or []
                block_list = ", ".join(f"Block {b}" for b in blocks)
                if block_list:
                    lines.append(f"- {summary} ({block_list})")
                else:
                    lines.append(f"- {summary}")

        _render("direct_answers", "Direct answers")
        _render("supporting_facts", "Supporting facts")
        _render("related_details", "Related details")

        gaps = digest.get("gaps", [])
        if gaps:
            lines.append("Gaps:")
            for gap in gaps:
                if isinstance(gap, dict):
                    lines.append(f"- {gap.get('summary', str(gap))}")
                else:
                    lines.append(f"- {gap}")

        return "\n".join(lines) if lines else "(digest empty)"

    def _build_source_section(self, blocks: list[str]) -> str:
        if not blocks:
            return ""
        lines = ["## Source Blocks"]
        for idx, text in enumerate(blocks, 1):
            lines.append(f"- [Block {idx}] {_shorten(text)}")
        return "\n".join(lines)

    def _fallback_answer(self, question: str, blocks: list[str], digest: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append(
            f"## Direct Answer\nThe archives provide {len(blocks)} context blocks relevant to the query '{question}'."
        )

        if digest.get("direct_answers"):
            lines.append("\n## Canonical Details")
            for item in digest["direct_answers"]:
                summary = item.get("summary", "")
                blocks_list = ", ".join(f"[Block {b}]" for b in item.get("blocks", []))
                lines.append(f"- {summary} {blocks_list}".strip())

        if digest.get("supporting_facts"):
            lines.append("\n### Additional Supporting Facts")
            for item in digest["supporting_facts"]:
                summary = item.get("summary", "")
                blocks_list = ", ".join(f"[Block {b}]" for b in item.get("blocks", []))
                lines.append(f"- {summary} {blocks_list}".strip())

        if digest.get("related_details"):
            lines.append("\n## Additional Insights")
            for item in digest["related_details"]:
                summary = item.get("summary", "")
                blocks_list = ", ".join(f"[Block {b}]" for b in item.get("blocks", []))
                lines.append(f"- {summary} {blocks_list}".strip())

        if digest.get("gaps"):
            lines.append("\n## Archive Gaps")
            for item in digest["gaps"]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('summary', '')}")
                else:
                    lines.append(f"- {item}")

        source_section = self._build_source_section(blocks)
        if source_section:
            lines.append("\n" + source_section)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Runnable interface
    # ------------------------------------------------------------------
    def invoke(self, input: dict[str, Any], config: dict | None = None) -> dict[str, Any]:  # type: ignore[override]
        blocks = _normalize_context_blocks(input.get("context_blocks", []))
        question = input.get("query", "").strip()

        if not blocks:
            logger.warning("DirectAnswerChain invoked without context blocks")
            return {
                "answer": (
                    "The archives hold no passages relevant to this request. "
                    "Provide or retrieve context blocks before asking for a synthesis."
                ),
                "used_blocks": 0,
                "context_digest": _empty_digest(),
                "source_blocks": [],
            }

        digest = self._build_digest(question, blocks)
        digest_text = self._digest_to_text(digest)

        # Prepare conversation history snippet if provided
        history = input.get("conversation_history") or []
        history_lines: list[str] = []
        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user").capitalize()
                content = msg.get("content", "").strip()
                if not content:
                    continue
                history_lines.append(f"{role}: {_shorten(content, width=160)}")
        history_instructions = (
            "Previous conversation suggests continuity:\n" + "\n".join(history_lines) + "\n\n"
            "Build on this timeline naturally.\n"
            if history_lines
            else ""
        )

        context_text = _format_context_blocks(blocks)

        if isinstance(self.answer_llm, _FallbackChatModel):
            final_answer = self._fallback_answer(question, blocks, digest)
        else:
            prompt = FINAL_PROMPT.format_prompt(
                question=question,
                context=context_text,
                digest=digest_text,
                history_instructions=history_instructions,
            )
            response = self.answer_llm.invoke(prompt.to_messages())
            final_answer = response.content.strip()

            # Ensure the source section is appended even if the LLM forgot
            if "Source Blocks" not in final_answer:
                source_section = self._build_source_section(blocks)
                if source_section:
                    final_answer = f"{final_answer}\n\n{source_section}"

        source_blocks = [
            {
                "index": idx,
                "text": text,
            }
            for idx, text in enumerate(blocks, 1)
        ]

        return {
            "answer": final_answer,
            "used_blocks": len(blocks),
            "context_digest": digest,
            "digest_text": digest_text,
            "source_blocks": source_blocks,
        }
