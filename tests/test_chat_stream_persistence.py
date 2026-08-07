"""Regression coverage for persistence of completed chat streams."""

from src.api.main import _final_chat_event_content


def test_final_chat_event_content_accepts_modern_react_schema():
    event = {"type": "final", "content": "Grounded modern answer"}

    assert _final_chat_event_content(event, "") == "Grounded modern answer"


def test_final_chat_event_content_preserves_legacy_and_buffer_fallbacks():
    assert (
        _final_chat_event_content(
            {"type": "final", "answer": "Legacy answer", "content": "Modern answer"},
            "buffered answer",
        )
        == "Legacy answer"
    )
    assert _final_chat_event_content({"type": "final"}, "buffered answer") == "buffered answer"
