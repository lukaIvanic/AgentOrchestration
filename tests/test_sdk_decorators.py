import pytest

from src.sdk.decorators import on_event


def test_on_event_rejects_blank_event_type():
    with pytest.raises(
        ValueError,
        match="event_type must be a non-empty string",
    ):
        on_event("")


def test_on_event_rejects_whitespace_only_event_type():
    with pytest.raises(
        ValueError,
        match="event_type must be a non-empty string",
    ):
        on_event("   ")


def test_on_event_rejects_non_string_event_type():
    with pytest.raises(TypeError, match="event_type must be a string"):
        on_event(None)


def test_on_event_marks_handler_with_event_type():
    @on_event("agent.started")
    async def handle_started():
        return "ok"

    assert handle_started.__event_handler__ == "agent.started"
