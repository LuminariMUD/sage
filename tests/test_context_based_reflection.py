"""Deterministic context-grounding coverage for the reflection chain."""

import json
from types import SimpleNamespace

import pytest

from src.agents.langchain.chains import reflection as reflection_module


class ContextFactCheckerDouble:
    """Return stable evaluations while verifying the authored prompt content."""

    async def ainvoke(self, messages):
        prompt = "\n".join(str(message.content) for message in messages)

        if "The elves speak in Tal" in prompt:
            result = {
                "is_grounded": False,
                "unsupported_claims": ["The elves speak in Tal"],
                "context_sufficient": True,
                "missing_aspects": [],
                "suggested_queries": [],
                "confidence_score": 0.4,
                "reasoning": "The context attributes Tal to Crystal Dwarves, not elves.",
            }
        elif "The Crystal Dwarves communicate in Tal" in prompt:
            result = {
                "is_grounded": True,
                "unsupported_claims": [],
                "context_sufficient": True,
                "missing_aspects": [],
                "suggested_queries": [],
                "confidence_score": 0.95,
                "reasoning": "Every claim is present in the supplied context.",
            }
        else:
            assert "Elves speak an ancient melodic language" in prompt
            result = {
                "is_grounded": False,
                "unsupported_claims": ["Elves speak an ancient melodic language"],
                "context_sufficient": False,
                "missing_aspects": ["The language spoken by elves"],
                "suggested_queries": ["canonical elven language"],
                "confidence_score": 0.3,
                "reasoning": "The supplied context contains no language information.",
            }

        return SimpleNamespace(content=json.dumps(result))


@pytest.fixture
def reflection(monkeypatch):
    monkeypatch.setattr(
        reflection_module,
        "text_profile_is_ready",
        lambda capability: False,
    )
    chain = reflection_module.ReflectionChain()
    chain.llm = ContextFactCheckerDouble()
    return chain


async def test_tal_misattribution(reflection):
    context_blocks = [
        "Crystal Dwarves speak in Tal, a language of harmonic resonance.",
        "Elves emerged from moonlight and memory.",
    ]

    result = await reflection.reflect_on_answer(
        answer="The elves speak in Tal, their voices resonating like symphonies.",
        question="Tell me about elven language",
        context_blocks=context_blocks,
    )

    assert not result.is_grounded
    assert result.needs_revision
    assert result.confidence_score < 0.7
    assert any("elves speak" in claim.lower() for claim in result.unsupported_claims)


async def test_correct_attribution(reflection):
    context_blocks = [
        "Crystal Dwarves speak in Tal, a language of harmonic resonance.",
        "They communicate through vibrations and musical tones.",
    ]

    result = await reflection.reflect_on_answer(
        answer="The Crystal Dwarves communicate in Tal through harmonic resonance.",
        question="How do Crystal Dwarves communicate?",
        context_blocks=context_blocks,
    )

    assert result.is_grounded
    assert not result.needs_revision
    assert result.confidence_score > 0.7


async def test_missing_context(reflection):
    result = await reflection.reflect_on_answer(
        answer="Elves speak an ancient melodic language passed down through generations.",
        question="What language do elves speak?",
        context_blocks=["Elves are an ancient race with pointed ears."],
    )

    assert not result.context_sufficient
    assert result.needs_revision
    assert result.suggested_queries == ["canonical elven language"]
