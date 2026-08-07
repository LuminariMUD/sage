"""Instruction-following regressions for grounded direct answers."""

from src.agents.langchain.chains.direct_answer import (
    DirectAnswerChain,
    _FallbackChatModel,
    _requests_compact_answer,
)


class _Response:
    content = "The Last War came first [Block 1]."


class _AnswerModel:
    def invoke(self, _messages):
        return _Response()


def _offline_chain() -> DirectAnswerChain:
    chain = DirectAnswerChain.__new__(DirectAnswerChain)
    chain.answer_llm = _AnswerModel()
    chain.digest_llm = _FallbackChatModel("digest")
    return chain


def test_compact_request_markers_are_detected():
    assert _requests_compact_answer("Answer in one concise sentence: what happened?")
    assert _requests_compact_answer("Briefly explain what happened.")
    assert not _requests_compact_answer("Explain what happened.")


def test_compact_answer_does_not_gain_source_appendix():
    result = _offline_chain().invoke(
        {
            "query": "Answer in one concise sentence: what happened first?",
            "context_blocks": ["The Last War erupted before the caves were sealed."],
        }
    )

    assert result["answer"] == "The Last War came first [Block 1]."


def test_default_answer_keeps_source_appendix():
    result = _offline_chain().invoke(
        {
            "query": "What happened first?",
            "context_blocks": ["The Last War erupted before the caves were sealed."],
        }
    )

    assert "## Source Blocks" in result["answer"]
