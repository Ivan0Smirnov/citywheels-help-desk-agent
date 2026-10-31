import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from citywheels.agent import run_agent
from citywheels.gemini import GeminiModel, MissingApiKey
from citywheels.prompt import SYSTEM_PROMPT

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

_UNAVAILABLE = (
    "The assistant is unavailable right now. Please contact our staff: "
    "help@citywheels.example, +48 000 000 000."
)


def _answer(question: str, model, verbose: bool) -> bool:
    """Print the answer to stdout; return False when the model call failed."""
    try:
        result = run_agent(question, model, SYSTEM_PROMPT)
    except Exception as exc:
        print(f"{_UNAVAILABLE}\n({type(exc).__name__}: {exc})", file=sys.stderr)
        return False
    if verbose:
        results = [m["result"] for m in result.messages if m["role"] == "tool"]
        for call, tool_result in zip(result.tool_calls, results):
            print(
                f"[tool] {call.name}({json.dumps(call.args)}) -> {json.dumps(tool_result)}",
                file=sys.stderr,
            )
    print(result.answer)
    return True


def main(argv=None, model_factory=GeminiModel.from_env, stdin=sys.stdin) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m citywheels", description="CityWheels help desk assistant."
    )
    parser.add_argument("question", nargs="*", help="Ask one question; omit for interactive mode.")
    parser.add_argument("--verbose", action="store_true", help="Show tool calls on stderr.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    try:
        model = model_factory()
    except MissingApiKey:
        print(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and put your key there.",
            file=sys.stderr,
        )
        return 2

    if args.question:
        return 0 if _answer(" ".join(args.question), model, args.verbose) else 1

    print("CityWheels help desk. Ask a question, or press Enter to quit.", file=sys.stderr)
    for line in stdin:
        question = line.strip()
        if not question:
            break
        _answer(question, model, args.verbose)
    return 0


if __name__ == "__main__":
    load_dotenv(ENV_FILE)
    sys.exit(main())
