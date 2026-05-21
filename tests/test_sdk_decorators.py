import asyncio

import pytest

from src.sdk.decorators import on_event


@pytest.mark.parametrize("event_type", ["", "   ", "\t\n"])
def test_on_event_rejects_blank_event_type(event_type):
    with pytest.raises(
        ValueError,
        match="event_type must be a non-empty string",
    ):
        on_event(event_type)


def test_on_event_rejects_non_string_event_type():
    with pytest.raises(TypeError, match="event_type must be a string"):
        on_event(None)


def test_on_event_marks_handler_with_event_type():
    @on_event("agent.started")
    async def handle_started():
        return "ok"

    assert handle_started.__event_handler__ == "agent.started"


def test_on_event_strips_surrounding_event_type_whitespace():
    @on_event("  agent.started  ")
    async def handle_started():
        return "ok"

    assert handle_started.__event_handler__ == "agent.started"


def test_on_event_preserves_wrapped_handler_behavior():
    seen_payloads = []

    @on_event("agent.started")
    async def handle_started(payload):
        seen_payloads.append(payload)
        return "ok"

    payload = {"agent_id": "agent-1"}

    assert asyncio.run(handle_started(payload)) == "ok"
    assert seen_payloads == [payload]
