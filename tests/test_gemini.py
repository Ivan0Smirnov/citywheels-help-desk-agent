import pytest
from google.genai import types

from citywheels.agent import TOOLS, ToolCall, run_agent
from citywheels.gemini import GeminiModel, _config, _to_contents, _to_reply
from citywheels.prompt import SYSTEM_PROMPT


def response(*parts):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def call_part(name, args, id=None):
    return types.Part(function_call=types.FunctionCall(name=name, args=args, id=id))


class FakeClient:
    """Stands in for genai.Client: records requests, returns scripted responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        return self.responses.pop(0)


def test_request_conversion():
    raw = types.Content(role="model", parts=[call_part("search_policies", {"query": "x"}, "a")])
    messages = [
        {"role": "user", "text": "question"},
        {"role": "assistant", "text": None, "tool_calls": [], "raw": raw},
        {"role": "tool", "name": "search_policies", "id": "a", "result": [{"section": "s"}]},
        {"role": "tool", "name": "get_booking", "id": "b", "result": {"found": False}},
    ]

    user, model_turn, tool_turn = _to_contents(messages)

    assert (user.role, user.parts[0].text) == ("user", "question")
    assert model_turn is raw
    assert tool_turn.role == "user"
    responses = [p.function_response for p in tool_turn.parts]
    assert [(r.name, r.id) for r in responses] == [("search_policies", "a"), ("get_booking", "b")]
    assert responses[0].response == {"result": [{"section": "s"}]}


def test_assistant_without_raw_is_rebuilt():
    message = {
        "role": "assistant",
        "text": None,
        "tool_calls": [ToolCall("get_booking", {"booking_id": "CW-1001"}, "c")],
        "raw": None,
    }

    [content] = _to_contents([message])

    assert content.role == "model"
    call = content.parts[0].function_call
    assert (call.name, call.args, call.id) == ("get_booking", {"booking_id": "CW-1001"}, "c")


def test_config():
    config = _config("prompt", TOOLS)

    assert config.system_instruction == "prompt"
    declarations = config.tools[0].function_declarations
    assert [d.name for d in declarations] == [t.name for t in TOOLS]
    assert declarations[0].parameters_json_schema == TOOLS[0].parameters
    assert config.automatic_function_calling.disable is True
    assert config.temperature == 0


@pytest.mark.parametrize(
    "resp, text, calls",
    [
        (response(types.Part(text="Hello.")), "Hello.", ()),
        (
            response(types.Part(text="thinking", thought=True), types.Part(text="Answer.")),
            "Answer.",
            (),
        ),
        (
            response(call_part("get_booking", {"booking_id": "CW-1002"}, "x")),
            None,
            (ToolCall("get_booking", {"booking_id": "CW-1002"}, "x"),),
        ),
        (types.GenerateContentResponse(candidates=[]), None, ()),
    ],
    ids=["text", "thought-skipped", "function-call", "no-candidate"],
)
def test_reply_parsing(resp, text, calls):
    reply = _to_reply(resp)

    assert reply.text == text
    assert reply.tool_calls == calls


def test_adapter_with_run_agent():
    first = response(call_part("get_booking", {"booking_id": "CW-1002"}, "c1"))
    client = FakeClient(first, response(types.Part(text="CW-1002 is an e-bike booking.")))

    result = run_agent("What is CW-1002?", GeminiModel(client, "test-model"), SYSTEM_PROMPT)

    assert result.answer == "CW-1002 is an e-bike booking."
    assert [r["model"] for r in client.requests] == ["test-model", "test-model"]
    second = client.requests[1]["contents"]
    assert second[1] is first.candidates[0].content
    booking = second[2].parts[0].function_response.response["result"]
    assert booking["bike_type"] == "e-bike"


def test_system_prompt():
    for fragment in [
        "Wednesday 2026-06-10 09:00",
        "calculate_refund",
        "was not found",
        "help@citywheels.example",
        "cannot cancel",
    ]:
        assert fragment in SYSTEM_PROMPT
