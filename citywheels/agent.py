import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from citywheels.bookings import get_booking
from citywheels.policies import search_policies
from citywheels.refund import refund_for_booking

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5
FALLBACK_ANSWER = (
    "Sorry, I could not answer that. Please contact our staff: "
    "help@citywheels.example, +48 000 000 000."
)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict
    id: str | None = None


@dataclass(frozen=True)
class ModelReply:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    # The provider's own reply object, replayed untouched by its adapter: Gemini attaches
    # thought signatures to tool-call parts that a follow-up request may need back.
    raw: Any = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    function: Callable[..., Any]


class Model(Protocol):
    def generate(
        self, system_prompt: str, messages: list[dict], tools: list[ToolSpec]
    ) -> ModelReply: ...


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)


def _string_params(**properties: str) -> dict:
    return {
        "type": "object",
        "properties": {
            name: {"type": "string", "description": description}
            for name, description in properties.items()
        },
        "required": list(properties),
    }


TOOLS = [
    ToolSpec(
        name="search_policies",
        description=(
            "Search the CityWheels policy documents (prices, cancellations and refunds, FAQ: "
            "opening hours, age limits, payment, rules). Returns the most relevant sections, "
            "or an empty list when the documents do not cover the question."
        ),
        parameters=_string_params(query="Keywords or a question in English."),
        function=search_policies,
    ),
    ToolSpec(
        name="get_booking",
        description=(
            "Get the details of one booking by its number, e.g. CW-1001. Returns "
            '{"found": false, "reason": ...} when there is no such booking.'
        ),
        parameters=_string_params(booking_id="Booking number, e.g. CW-1001."),
        function=get_booking,
    ),
    ToolSpec(
        name="calculate_refund",
        description=(
            "Calculate how much the customer gets back if they cancel the booking now. "
            "The amounts are computed by code from the cancellation rules: always use this "
            "tool for refund amounts and never calculate them yourself."
        ),
        parameters=_string_params(booking_id="Booking number, e.g. CW-1001."),
        function=refund_for_booking,
    ),
]


def _check_args(spec: ToolSpec, args: Any) -> str | None:
    """Return an error message, or None when `args` matches the declared parameters exactly.

    Model output is untrusted: only declared parameters may reach a tool, because the tool
    functions also accept file paths (bookings_path, policies_dir) for tests.
    """
    if not isinstance(args, dict):
        return "arguments must be an object"
    declared = spec.parameters["properties"]
    unknown = sorted(set(args) - set(declared))
    if unknown:
        return f"unknown arguments: {', '.join(unknown)}"
    missing = [name for name in spec.parameters["required"] if name not in args]
    if missing:
        return f"missing arguments: {', '.join(missing)}"
    for name, value in args.items():
        if declared[name]["type"] == "string" and not isinstance(value, str):
            return f"argument {name} must be a string"
    return None


def _run_tool(call: ToolCall, tools: list[ToolSpec]) -> Any:
    spec = next((t for t in tools if t.name == call.name), None)
    if spec is None:
        return {"error": f"unknown tool: {call.name}"}
    problem = _check_args(spec, call.args)
    if problem:
        return {"error": f"invalid arguments for {call.name}: {problem}"}
    try:
        return spec.function(**call.args)
    except Exception:
        logger.exception("tool %s failed with args %r", call.name, call.args)
        return {"error": "The tool failed. Tell the customer to contact the staff."}


def run_agent(
    question: str,
    model: Model,
    system_prompt: str,
    tools: list[ToolSpec] = TOOLS,
    max_rounds: int = MAX_ROUNDS,
) -> AgentResult:
    messages: list[dict] = [{"role": "user", "text": question}]
    calls: list[ToolCall] = []
    for _ in range(max_rounds):
        reply = model.generate(system_prompt, messages, tools)
        if not reply.tool_calls:
            answer = (reply.text or "").strip() or FALLBACK_ANSWER
            return AgentResult(answer, calls, messages)
        messages.append(
            {
                "role": "assistant",
                "text": reply.text,
                "tool_calls": list(reply.tool_calls),
                "raw": reply.raw,
            }
        )
        for call in reply.tool_calls:
            calls.append(call)
            messages.append(
                {
                    "role": "tool",
                    "name": call.name,
                    "id": call.id,
                    "result": _run_tool(call, tools),
                }
            )
    return AgentResult(FALLBACK_ANSWER, calls, messages)
