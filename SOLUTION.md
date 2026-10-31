# CityWheels help desk agent

A command-line AI agent that answers CityWheels customer questions from the shop's own documents and
booking data. The model decides which tool to use; my code runs the tool and computes every amount.

**Python 3.10 - Google Gemini API - no agent framework - 105 offline tests - evaluation 17 / 17**

Contents: [Quick start](#quick-start) - [Model](#model-and-provider) -
[How it works](#how-the-agent-works) - [Evaluation](#evaluation) -
[AI assistants](#how-i-used-ai-coding-assistants) - [Limitations](#limitations) -
[Next steps](#what-i-would-do-next)

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # put your GEMINI_API_KEY in .env
```

| I want to... | Command |
| --- | --- |
| Ask one question | `python -m citywheels "How much do I get back if I cancel CW-1002?"` |
| Chat | `python -m citywheels` (empty line quits) |
| See which tools were used | add `--verbose` |
| Run the tests | `python -m pytest` (no network, no API key) |
| Run the evaluation | `python eval/run.py` (real API, writes `eval/results.md`) |

The tests also run in GitHub Actions on every push (`.github/workflows/tests.yml`).

---

## Model and provider

**Google Gemini, free tier, model `gemini-3.5-flash-lite`**, through the official `google-genai` SDK.
Change it with `GEMINI_MODEL` in `.env`.

Why Gemini: free, supports tool calling, nothing to run locally.

Why no framework: the tool-calling loop is the heart of the assignment and takes about 190 lines
(`citywheels/agent.py`). Writing it myself means I can explain every step and test it with a fake model.

Why this exact model - I chose it by measuring, not from memory:

| Model | What happened |
| --- | --- |
| `gemini-2.5-flash` | 404: no longer available to new users |
| `gemini-3.8-flash` | 503 "high demand"; one request took about 4 minutes |
| `gemini-3.5-flash` | correct answers, but only 20 requests per day on the free tier |
| `gemini-3.5-flash-lite` | 500 requests per day, 4-13 s per question, 17 / 17 in the evaluation |

I use a fixed model version, not a `-latest` alias, so evaluation runs stay comparable.

---

## How the agent works

```
customer question
      |
      v
  run_agent  -- question + rules + tool list -->  Gemini
      ^                                              |
      |                                    "call calculate_refund(CW-1002)"
      |                                              |
      +---- tool result <--- my code runs the tool <-+
      |
   (repeat until Gemini answers with text, at most 5 rounds)
      |
      v
   answer
```

### The loop - `citywheels/agent.py`

1. Send the system prompt, the conversation so far and the tool list to the model.
2. If the model answers with text, that is the answer.
3. If it asks for tools, run each one, add the results to the conversation, go back to 1.
4. After 5 rounds without an answer, reply with a fixed message that points to the staff.

Safety built into the loop:

- **It never crashes.** An unknown tool, wrong arguments or an error inside a tool goes back to the
  model as `{"error": ...}`, and the model tells the customer to contact the staff.
- **The model cannot pass anything unexpected.** Only the declared arguments of a tool are accepted
  (text must be text, numbers must be numbers). The tool functions also accept a data file path for
  tests; the model can never reach it.

The loop does not know about Gemini. `citywheels/gemini.py` translates between the loop and the
Gemini API: it converts the messages, sends the model's own turns back unchanged (Gemini needs its
"thought signatures" in multi-turn tool calls), turns off the SDK's automatic tool calling, and uses
temperature 0.

### The tools

| Tool | What it does | Worth knowing |
| --- | --- | --- |
| `search_policies(query)` | Finds the best matching sections of `data/policies/*.md` | BM25 ranking over the 22 `##` sections, plain Python. Returns whole sections, or nothing if no word matches. |
| `get_booking(booking_id)` | Returns one booking from `data/bookings.json` | Accepts `cw-1002 `. Unknown number -> `not_found`, not a booking number (`12345`) -> `invalid_id`. A broken data file raises an error instead of saying "not found". |
| `calculate_refund(booking_id)` | Refund if the booking is cancelled now | Computed in code with `Decimal`. Every rule has a test, including exactly 48 h and 24 h before the start. |
| `calculate_late_fee(bike_type, hours_late)` | Fee for returning a bike late | 1.5 x hourly price x started hours. Added after the evaluation showed the gap (see below). |

"Now" is fixed at 2026-06-10 09:00 Europe/Warsaw, as the README requires.

One rule the documents do not cover: a confirmed booking whose start time has already passed. I chose
the literal reading of the rules - "less than 24 hours" - so 0 % of the rental and the deposit back.

### The instructions to the model - `citywheels/prompt.py`

The system prompt gives the current date and eight rules:

1. Answer only from the tools, never from general knowledge.
2. Search the policies before answering about rules or prices.
3. Take refunds and late fees only from their tools; never calculate amounts yourself.
4. You cannot cancel or change bookings - never say you did.
5. For an unknown booking, say "Booking ... was not found" and ask to check the number.
6. If the tools do not answer, or the question is not about CityWheels, say so and give the staff contact.
7. Quote times and prices as the documents write them.
8. Answer briefly, in the customer's language.

---

## Evaluation

### What is tested

`eval/questions.json` has **17 questions**: 5 refunds, 2 bookings that cannot be cancelled, 2 unknown
or invalid booking numbers, 1 booking fact, 4 policy questions and 3 questions the agent must refuse.

The expected refund amounts were written by a separate AI agent that worked only from the documents.
They match `calculate_refund`, which makes them an independent check of my code.

### How it is checked

`python eval/run.py` asks every question and marks it **PASS** only if:

- the expected tool was called,
- the answer contains every required phrase (for example `340`),
- the answer contains none of the forbidden phrases (for example `has been cancelled`).

Numbers must match as whole numbers (`50` does not match `150` or `50%`), and `8:00` equals `08:00`.
API problems are reported as **ERROR**, separately from wrong answers.

### Result

**17 / 17 passed** on `gemini-3.5-flash-lite` (2026-10-31, 145 s). Full report: `eval/results.md`.

### How I got there

| Run | Model | Result | What I learned |
| --- | --- | --- | --- |
| 1 | `3.8-flash` | 0 / 17, all errors | Overloaded (503), then the daily limit. My `.env` still pointed at this model. |
| 2 | `3.5-flash` | 6 passed, 11 errors | Every answered question was right, but the free tier stops at 20 requests per day. |
| 3 | `3.5-flash-lite` | 15 / 17 | Two real problems, below. |
| 4 | `3.5-flash-lite` | **17 / 17** | After fixing both. |

The two failures in run 3:

- **Late return fee - the agent's gap.** Asked about returning a city bike 2 hours late, the agent
  repeated the rule but never said 12 EUR. There was no tool for it and the prompt forbids
  calculating money. *Fix:* the `calculate_late_fee` tool, so the amount comes from code, like refunds.
- **Saturday hours - my mistake in the test.** "What time do you open on Saturday?" was answered
  "We open at 08:00", which is correct, but my check also required the closing time 20:00.
  *Fix:* the check now asks only for 08:00. I changed this expectation after seeing the result,
  so I state the reason here on purpose.

Runs 1 and 2 also improved the evaluation script: it now spaces requests to the model's
per-minute limit, stops on a daily-quota error instead of retrying it, and keeps error messages short.

**What 17 / 17 means:** the agent handles these 17 cases in this run. Model answers can vary between
runs, and phrase checks cannot judge everything, so it is not proof that the agent never makes mistakes.

### Comparing two models

On the 6 questions both models answered (all refunds and one booking that cannot be cancelled):

| | `gemini-3.5-flash` | `gemini-3.5-flash-lite` |
| --- | --- | --- |
| Correct | 6 / 6 | 6 / 6 |
| Time per question | 17-117 s | 5-12 s |
| Tool calls per question | more (searched the policies even after `calculate_refund`) | 1-3 |
| Free-tier requests per day | 20 | 500 |

For this task the smaller model was just as correct, much faster, and the only one I could evaluate
fully on the free tier.

---

## How I used AI coding assistants

I used **Claude Code** for planning, writing code and tests, reviewing diffs and running checks. I made
the decisions - model, retry policy, the rule the documents do not cover - and reviewed each change
before merging. Every feature went through its own branch and pull request (10 in total). A second
Claude agent, in a separate git worktree, wrote the evaluation questions without seeing my refund
code.

Where its output was wrong - each problem was caught by something different: me, CI, the
evaluation, or code review.

| # | What the assistant did wrong | Caught by | What changed |
| --- | --- | --- | --- |
| 1 | **Picked the model from memory.** `gemini-2.5-flash` was retired (404); the next one, `3.8-flash`, was overloaded (503, 4 min per request); then it recommended `3.5-flash` for its speed without checking the free-tier limit of 20 requests per day, so the evaluation died halfway. | Smoke test, then **me**: I checked the limits on the AI Studio rate-limit page. | I chose `gemini-3.5-flash-lite` (500 requests per day). |
| 2 | **Kept a needed file out of git.** It said the empty `citywheels/__init__.py` could wait, while `pyproject.toml` declared that package and CI ran `pip install -e`. Worked locally, failed on GitHub (586c4f1). | **CI** (red build) | File committed (505bccc). |
| 3 | **Asked me to commit an untested config.** It told me to commit `pyproject.toml` before anyone had installed the project with it. | **Me** - I asked if we should really commit it already. | Installed and ran the tests first, committed after. |
| 4 | **The eval script wasted the daily quota.** It retried every API error, including "daily limit exceeded, retry in 20 hours", spending requests that could never succeed. | **The evaluation** - runs ending with only errors | No retry for daily-quota errors, remaining questions skipped, requests spaced to the per-minute limit. |
| 5 | **Wrote a test that could not fail.** The assertion `A or B` had an `A` that was never true and a `B` that was always true, so the test passed whatever the code did. | **Reviewing the diff** | Rewritten to check that the exact same object is sent back. |
| 6 | **The second agent's eval checks were too weak.** `"50"` also matched `"150"` and `"50%"`; nothing failed an answer claiming "your booking has been cancelled"; one requested question was missing. | **Reviewing its file** | Whole-number matching, forbidden phrases on all refund questions, missing question added. |

What I take from it: every layer caught something the others did not, so I kept all of them -
my own review, CI on every push, and the evaluation.

---

## Limitations

- **No identity check.** Anyone with a booking number sees that booking. Fine for this sample data
  (no personal details), not for a real shop.
- **Search matches words, not meaning.** "e-bike" vs "electric bike" only share "bike", and "car park"
  matches "Riverside Park". The documents are small (about 4.5 KB) and would fit in the prompt; the
  search tool exists because the assignment asks for one.
- **No memory.** Each question is answered on its own, so follow-ups like "and if I cancel tomorrow?"
  do not work yet.
- **The agent cannot act.** It explains refunds but cannot cancel; the customer contacts the staff.
- **Hourly prices live in two places**, the code and `prices.md`. A test fails if they drift apart.
- **Free-tier API.** Daily limits, overload errors, and the model behind a name can change (a quota
  error for `gemini-3.5-flash` named the quota of `gemini-3.6-flash`).
- **Small evaluation.** 17 questions with phrase checks catch regressions; they do not measure
  quality in general.

---

## What I would do next

1. **Conversation memory**, so "and if I cancel tomorrow?" works - `calculate_refund` would take the
   cancellation time.
2. **Repeat the evaluation several times per model** and report the pass rate, because answers vary
   between runs.
3. **More questions**, including other languages, and an automatic check that every number in an
   answer comes from a tool result.
4. **Read the hourly prices from `prices.md`** instead of keeping a copy in code.
