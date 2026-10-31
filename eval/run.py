"""Run the agent on every question in eval/questions.json and write eval/results.md.

Usage: python eval/run.py [--rpm 15]   (needs GEMINI_API_KEY in .env; calls the real API)
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from citywheels.__main__ import ENV_FILE
from citywheels.evaluation import RateLimitedModel, load_questions, render_markdown, run_eval
from citywheels.gemini import GeminiModel, MissingApiKey

EVAL_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CityWheels evaluation.")
    # 15 = free-tier requests per minute for gemini-3.5-flash-lite (AI Studio rate-limit page).
    parser.add_argument("--rpm", type=float, default=15, help="Max model requests per minute.")
    args = parser.parse_args()
    load_dotenv(ENV_FILE)
    try:
        model = GeminiModel.from_env()
    except MissingApiKey:
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and put your key there.",
              file=sys.stderr)
        return 2

    questions = load_questions(EVAL_DIR / "questions.json")
    print(
        f"Running {len(questions)} questions on {model.model_name}, max {args.rpm:g} requests/min...",
        file=sys.stderr,
    )
    run_at, start = datetime.now(), time.monotonic()
    results = run_eval(
        questions,
        RateLimitedModel(model, args.rpm),
        progress=lambda r: print(f"{r.status:5} {r.id} ({r.seconds:.1f} s)", file=sys.stderr),
    )
    report = render_markdown(results, model.model_name, run_at, time.monotonic() - start)
    (EVAL_DIR / "results.md").write_text(report, encoding="utf-8")
    passed = sum(r.status == "PASS" for r in results)
    print(f"Passed {passed} / {len(results)}. Report: eval/results.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
