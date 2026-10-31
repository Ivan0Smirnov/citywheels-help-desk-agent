import copy
import logging

import pytest

from citywheels.agent import (
    FALLBACK_ANSWER,
    MAX_ROUNDS,
    TOOLS,
    ModelReply,
    ToolCall,
    ToolSpec,
    run_agent,
)


class FakeModel:
    """Replays scripted replies and records what the loop sent on every call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, system_prompt, messages, tools):
        self.calls.append(
            {"system_prompt": system_prompt, "messages": copy.deepcopy(messages), "tools": tools}
        )
        return self.replies.pop(0)


def ask(*replies, **kwargs):
    model = FakeModel(*replies)
    return run_agent("question", model, "system prompt", **kwargs), model


def tool_results(model_call):
    return [m["result"] for m in model_call["messages"] if m["role"] == "tool"]


def test_tool_result_is_sent_back_to_model():
    result, model = ask(
        ModelReply(tool_calls=(ToolCall("get_booking", {"booking_id": "CW-1002"}, id="c1"),)),
        ModelReply(text="CW-1002 is an e-bike booking."),
    )

    assert result.answer == "CW-1002 is an e-bike booking."
    assert [c.name for c in result.tool_calls] == ["get_booking"]
    assert len(model.calls) == 2
    [booking] = tool_results(model.calls[1])
    assert booking["found"] is True
    assert booking["bike_type"] == "e-bike"
    tool_message = model.calls[1]["messages"][-1]
    assert (tool_message["name"], tool_message["id"]) == ("get_booking", "c1")


def test_calculate_refund_tool_runs_refund_code():
    _, model = ask(
        ModelReply(tool_calls=(ToolCall("calculate_refund", {"booking_id": "CW-1002"}),)),
        ModelReply(text="You get 340 EUR back."),
    )

    [refund] = tool_results(model.calls[1])
    assert refund["total_refund_eur"] == 340.0


def test_answer_without_tools():
    result, model = ask(ModelReply(text="We open at 08:00."))

    assert result.answer == "We open at 08:00."
    assert result.tool_calls == []
    assert len(model.calls) == 1
    assert model.calls[0]["system_prompt"] == "system prompt"
    assert model.calls[0]["messages"] == [{"role": "user", "text": "question"}]
    assert model.calls[0]["tools"] is TOOLS


def test_unknown_tool_returns_error_to_model():
    result, model = ask(
        ModelReply(tool_calls=(ToolCall("delete_booking", {"booking_id": "CW-1002"}),)),
        ModelReply(text="I cannot do that."),
    )

    assert result.answer == "I cannot do that."
    assert tool_results(model.calls[1]) == [{"error": "unknown tool: delete_booking"}]


@pytest.mark.parametrize(
    "args, problem",
    [
        ({}, "missing arguments: booking_id"),
        ({"booking_id": 1002}, "argument booking_id must be a string"),
        (
            {"booking_id": "CW-1002", "bookings_path": "/etc/passwd"},
            "unknown arguments: bookings_path",
        ),
        ("CW-1002", "arguments must be an object"),
    ],
)
def test_invalid_arguments_are_rejected(args, problem):
    called = []
    spy = ToolSpec(
        name="get_booking",
        description="",
        parameters=TOOLS[1].parameters,
        function=lambda **kwargs: called.append(kwargs),
    )

    _, model = ask(
        ModelReply(tool_calls=(ToolCall("get_booking", args),)),
        ModelReply(text="done"),
        tools=[spy],
    )

    assert tool_results(model.calls[1]) == [
        {"error": f"invalid arguments for get_booking: {problem}"}
    ]
    assert called == []


def test_tool_exception_returns_error_and_is_logged(caplog):
    def broken(**kwargs):
        raise FileNotFoundError("bookings.json")

    spec = ToolSpec("get_booking", "", TOOLS[1].parameters, broken)

    with caplog.at_level(logging.ERROR, logger="citywheels.agent"):
        result, model = ask(
            ModelReply(tool_calls=(ToolCall("get_booking", {"booking_id": "CW-1002"}),)),
            ModelReply(text="Please contact the staff."),
            tools=[spec],
        )

    assert result.answer == "Please contact the staff."
    assert tool_results(model.calls[1]) == [
        {"error": "The tool failed. Tell the customer to contact the staff."}
    ]
    assert "FileNotFoundError" in caplog.text


def test_stops_after_max_rounds():
    looping = ModelReply(tool_calls=(ToolCall("search_policies", {"query": "hours"}),))

    result, model = ask(*[looping] * (MAX_ROUNDS + 1))

    assert result.answer == FALLBACK_ANSWER
    assert len(model.calls) == MAX_ROUNDS
    assert len(result.tool_calls) == MAX_ROUNDS


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_answer_falls_back(text):
    result, _ = ask(ModelReply(text=text))

    assert result.answer == FALLBACK_ANSWER
    assert "help@citywheels.example" in FALLBACK_ANSWER


def test_tool_specs():
    assert {t.name for t in TOOLS} == {
        "search_policies",
        "get_booking",
        "calculate_refund",
        "calculate_late_fee",
    }
    for spec in TOOLS:
        assert spec.description
        assert spec.parameters["type"] == "object"
        assert spec.parameters["required"] == list(spec.parameters["properties"])


@pytest.mark.parametrize("hours_late", ["2", True, None])
def test_number_arguments_are_checked(hours_late):
    _, model = ask(
        ModelReply(
            tool_calls=(ToolCall("calculate_late_fee", {"bike_type": "city", "hours_late": hours_late}),)
        ),
        ModelReply(text="done"),
    )

    assert tool_results(model.calls[1]) == [
        {"error": "invalid arguments for calculate_late_fee: argument hours_late must be a number"}
    ]


def test_late_fee_tool_runs_fee_code():
    _, model = ask(
        ModelReply(
            tool_calls=(ToolCall("calculate_late_fee", {"bike_type": "city", "hours_late": 2}),)
        ),
        ModelReply(text="12 EUR"),
    )

    [fee] = tool_results(model.calls[1])
    assert fee["late_fee_eur"] == 12.0
