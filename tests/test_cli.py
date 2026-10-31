import io

from citywheels.__main__ import main
from citywheels.agent import ModelReply, ToolCall
from citywheels.gemini import MissingApiKey


class ScriptedModel:
    def __init__(self, *replies):
        self.replies = list(replies)

    def generate(self, system_prompt, messages, tools):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def run(argv, *replies, stdin=""):
    model = ScriptedModel(*replies)
    return main(argv, model_factory=lambda: model, stdin=io.StringIO(stdin))


def test_cli_one_shot(capsys):
    code = run(["What", "time?"], ModelReply(text="We open at 08:00."))

    assert code == 0
    assert capsys.readouterr().out == "We open at 08:00.\n"


def test_cli_interactive(capsys):
    code = run([], ModelReply(text="First."), ModelReply(text="Second."), stdin="q1\nq2\n\nq3\n")

    assert code == 0
    assert capsys.readouterr().out == "First.\nSecond.\n"


def test_cli_missing_key(capsys):
    def no_key():
        raise MissingApiKey

    code = main(["hi"], model_factory=no_key)

    assert code == 2
    err = capsys.readouterr().err
    assert "GEMINI_API_KEY is not set" in err
    assert "Traceback" not in err


def test_cli_api_error(capsys):
    code = run(["hi"], ConnectionError("network down"))

    assert code == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "unavailable" in err
    assert "help@citywheels.example" in err
    assert "ConnectionError: network down" in err


def test_cli_verbose(capsys):
    code = run(
        ["--verbose", "What is CW-1002?"],
        ModelReply(tool_calls=(ToolCall("get_booking", {"booking_id": "CW-1002"}),)),
        ModelReply(text="An e-bike booking."),
    )

    assert code == 0
    out, err = capsys.readouterr()
    assert out == "An e-bike booking.\n"
    assert '[tool] get_booking({"booking_id": "CW-1002"}) -> {"found": true' in err
