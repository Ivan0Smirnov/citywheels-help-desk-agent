import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from citywheels.agent import run_agent
from citywheels.prompt import SYSTEM_PROMPT

_NUMBER = re.compile(r"\d+(\.\d+)?")
_SHORT_TIME = re.compile(r"\b(\d):(\d\d)\b")
# Gemini free tier: a 429 naming a per-day quota will not clear by waiting (resets ~once a day),
# unlike a per-minute 429 or a 503 overload.
_DAILY_QUOTA = re.compile(r"per ?day", re.IGNORECASE)
_DAILY_QUOTA_ERROR = "daily quota exhausted"


@dataclass
class QuestionResult:
    id: str
    category: str
    status: str  # PASS, FAIL or ERROR
    answer: str = ""
    tools_called: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    seconds: float = 0.0
    error: str = ""


class RateLimitedModel:
    """Spaces generate() calls so a run stays under the provider's requests-per-minute limit."""

    def __init__(self, model, rpm: float, clock=time.monotonic, sleep=time.sleep):
        self.model = model
        self.interval = 60 / rpm
        self._clock = clock
        self._sleep = sleep
        self._last_call = None

    def generate(self, system_prompt, messages, tools):
        if self._last_call is not None:
            wait = self._last_call + self.interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()
        return self.model.generate(system_prompt, messages, tools)


def _describe(exc: Exception, limit: int = 160) -> str:
    text = f"{type(exc).__name__}: {exc}".splitlines()[0]
    return text if len(text) <= limit else text[: limit - 3] + "..."


def load_questions(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    return _SHORT_TIME.sub(r"0\1:\2", text)


def contains(text: str, needle: str) -> bool:
    """Case-insensitive match; a number only matches as a whole number ("50" not in "150")."""
    if _NUMBER.fullmatch(needle):
        pattern = rf"(?<![\d.,]){re.escape(needle)}(?:\.0+)?(?![\d%]|\.\d)"
        return re.search(pattern, text) is not None
    return _normalize(needle) in _normalize(text)


def check(question: dict, answer: str, tools_called: list[str]) -> list[str]:
    """Failed checks as readable strings; empty means PASS."""
    failures = [f"tool not called: {t}" for t in question["expected_tools"] if t not in tools_called]
    failures += [f"missing: {s!r}" for s in question["must_contain"] if not contains(answer, s)]
    failures += [f"forbidden: {s!r}" for s in question["must_not_contain"] if contains(answer, s)]
    return failures


def run_question(question: dict, model, sleep=time.sleep, retry_wait: float = 60) -> QuestionResult:
    """Run one question; an API error is retried once, then reported as ERROR, not FAIL.

    A daily-quota 429 is not retried: waiting a minute cannot clear it.
    """
    start = time.monotonic()
    for attempt in range(2):
        try:
            result = run_agent(question["question"], model, SYSTEM_PROMPT)
            break
        except Exception as exc:
            daily_quota = "429" in str(exc) and _DAILY_QUOTA.search(str(exc))
            if attempt == 0 and not daily_quota:
                sleep(retry_wait)
                continue
            prefix = f"{_DAILY_QUOTA_ERROR}: " if daily_quota else ""
            return QuestionResult(
                question["id"],
                question["category"],
                "ERROR",
                seconds=time.monotonic() - start,
                error=prefix + _describe(exc),
            )
    tools_called = [c.name for c in result.tool_calls]
    failures = check(question, result.answer, tools_called)
    return QuestionResult(
        question["id"],
        question["category"],
        "FAIL" if failures else "PASS",
        answer=result.answer,
        tools_called=tools_called,
        failures=failures,
        seconds=time.monotonic() - start,
    )


def run_eval(questions: list[dict], model, progress=None, **kwargs) -> list[QuestionResult]:
    """Run questions in order; after a daily-quota error the rest are skipped, not sent."""
    results = []
    for question in questions:
        if results and results[-1].error.startswith(_DAILY_QUOTA_ERROR):
            result = QuestionResult(
                question["id"], question["category"], "ERROR",
                error=f"{_DAILY_QUOTA_ERROR}: skipped, not sent",
            )
        else:
            result = run_question(question, model, **kwargs)
        if progress:
            progress(result)
        results.append(result)
    return results


def render_markdown(
    results: list[QuestionResult], model_name: str, run_at: datetime, seconds: float
) -> str:
    counts = {s: sum(r.status == s for r in results) for s in ("PASS", "FAIL", "ERROR")}
    lines = [
        "# Evaluation results",
        "",
        f"- Model: `{model_name}`",
        f"- Run: {run_at:%Y-%m-%d %H:%M}, {seconds:.0f} s",
        f"- **Passed: {counts['PASS']} / {len(results)}** "
        f"(failed {counts['FAIL']}, errors {counts['ERROR']})",
        "",
        "| Question | Category | Status | Tools called | Failed checks |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        problems = "; ".join(r.failures) or r.error
        lines.append(
            f"| {r.id} | {r.category} | {r.status} | {', '.join(r.tools_called)} | {problems} |"
        )
    details = [r for r in results if r.status != "PASS"]
    if details:
        lines += ["", "## Details of failed questions"]
        for r in details:
            lines += ["", f"### {r.id} ({r.status})", ""]
            lines += [f"- {problem}" for problem in r.failures] or [f"- {r.error}"]
            lines += ["", "Answer:", ""]
            lines += [f"> {line}" for line in (r.answer or "(no answer)").splitlines()]
    return "\n".join(lines) + "\n"
