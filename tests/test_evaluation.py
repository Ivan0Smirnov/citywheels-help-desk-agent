from datetime import datetime
from pathlib import Path

import pytest

from citywheels.agent import ModelReply, ToolCall
from citywheels.evaluation import (
    QuestionResult,
    check,
    contains,
    load_questions,
    render_markdown,
    run_question,
)

QUESTIONS = Path(__file__).resolve().parent.parent / "eval" / "questions.json"

REFUND_QUESTION = {
    "id": "refund-cw1002",
    "category": "refund",
    "question": "I want to cancel booking CW-1002. How much will I get back?",
    "expected_tools": ["calculate_refund"],
    "must_contain": ["340"],
    "must_not_contain": ["has been cancelled"],
}


class ScriptedModel:
    def __init__(self, *replies):
        self.replies = list(replies)

    def generate(self, system_prompt, messages, tools):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.mark.parametrize(
    "text, needle, expected",
    [
        ("You get **340 EUR** back.", "340", True),
        ("Total: 340.00 EUR", "340", True),
        ("Deposit of 150 EUR", "50", False),
        ("Refund of 50% of the price", "50", False),
        ("1,50 EUR", "50", False),
        ("Only the 50 EUR deposit.", "50", True),
        ("We open 8:00 to 20:00", "08:00", True),
        ("Open 08:00–20:00 every day", "20:00", True),
        ("I’ve cancelled it", "I've cancelled", True),
        ("Booking CW-9999 was Not Found.", "not found", True),
        ("Booking CW-9999 does not exist.", "not found", False),
    ],
)
def test_contains(text, needle, expected):
    assert contains(text, needle) is expected


def test_check_pass():
    assert check(REFUND_QUESTION, "You get 340 EUR back.", ["calculate_refund"]) == []


def test_check_missing_tool():
    assert check(REFUND_QUESTION, "You get 340 EUR back.", ["search_policies"]) == [
        "tool not called: calculate_refund"
    ]


def test_check_missing_phrase():
    assert check(REFUND_QUESTION, "You get 380 EUR back.", ["calculate_refund"]) == [
        "missing: '340'"
    ]


def test_check_forbidden_phrase():
    answer = "Your booking has been cancelled. You get 340 EUR back."
    assert check(REFUND_QUESTION, answer, ["calculate_refund"]) == [
        "forbidden: 'has been cancelled'"
    ]


def test_run_question_pass():
    model = ScriptedModel(
        ModelReply(tool_calls=(ToolCall("calculate_refund", {"booking_id": "CW-1002"}),)),
        ModelReply(text="You get 340 EUR back."),
    )

    result = run_question(REFUND_QUESTION, model, sleep=lambda s: None)

    assert (result.status, result.tools_called, result.failures) == (
        "PASS",
        ["calculate_refund"],
        [],
    )


def test_retry_then_error():
    waits = []
    model = ScriptedModel(ConnectionError("503"), ConnectionError("503 again"))

    result = run_question(REFUND_QUESTION, model, sleep=waits.append)

    assert result.status == "ERROR"
    assert result.error == "ConnectionError: 503 again"
    assert waits == [15]


def test_retry_then_pass():
    waits = []
    model = ScriptedModel(
        ConnectionError("503"),
        ModelReply(tool_calls=(ToolCall("calculate_refund", {"booking_id": "CW-1002"}),)),
        ModelReply(text="You get 340 EUR back."),
    )

    result = run_question(REFUND_QUESTION, model, sleep=waits.append)

    assert result.status == "PASS"
    assert waits == [15]


def test_render_markdown():
    results = [
        QuestionResult("q1", "refund", "PASS", "340 EUR", ["calculate_refund"]),
        QuestionResult("q2", "policy", "FAIL", "We open at 9.", ["search_policies"], ["missing: '08:00'"]),
        QuestionResult("q3", "refusal", "ERROR", error="ServerError: 503"),
    ]

    report = render_markdown(results, "gemini-test", datetime(2026, 10, 31, 12, 0), 42.4)

    assert "- Model: `gemini-test`" in report
    assert "- Run: 2026-10-31 12:00, 42 s" in report
    assert "**Passed: 1 / 3** (failed 1, errors 1)" in report
    assert "| q2 | policy | FAIL | search_policies | missing: '08:00' |" in report
    assert "### q2 (FAIL)" in report
    assert "> We open at 9." in report
    assert "### q3 (ERROR)" in report
    assert "- ServerError: 503" in report
    assert "### q1" not in report


def test_questions_file():
    questions = load_questions(QUESTIONS)
    required = {"id", "category", "question", "expected_tools", "must_contain", "must_not_contain"}

    assert len(questions) == 17
    assert len({q["id"] for q in questions}) == len(questions)
    assert all(required <= q.keys() for q in questions)
    assert sum(q["category"] == "refund" for q in questions) >= 2
    assert sum(q["expect_refusal"] for q in questions) >= 2
