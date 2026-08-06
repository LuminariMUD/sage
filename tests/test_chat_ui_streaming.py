"""Source-level contracts for the dependency-free browser chat client."""

from pathlib import Path

CHAT_UI = Path(__file__).resolve().parents[1] / "ui" / "chat-ui.html"


def _case_body(source: str, event_type: str, next_event_type: str) -> str:
    start = source.index(f"case '{event_type}':")
    end = source.index(f"case '{next_event_type}':", start)
    return source[start:end]


def test_terminal_sse_events_do_not_abort_the_response_body():
    """Terminal events render immediately but must still let fetch reach EOF."""
    source = CHAT_UI.read_text()

    terminal_cases = (
        ("final", "content"),
        ("complete", "error"),
        ("error", "tool_call"),
    )
    for event_type, next_event_type in terminal_cases:
        assert "return;" not in _case_body(source, event_type, next_event_type)

    assert "reader.releaseLock();" in source
