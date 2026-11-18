"""Score the help chat against synthetic questions, for one or more models.

Calls the real provider, so it costs money: it refuses to run without --approved-budget-usd, and stops
when the estimated spend reaches it. Uses the same system prompt, reference context and dosing guard
as production. Prints accuracy against 'expect'/'forbid', latency (median and p95) and tokens.
Nothing here is patient data. Not run in CI.

  ANTHROPIC_API_KEY=... python scripts/assistant_eval/run.py --models claude-opus-5-5 claude-sonnet-5-5 --approved-budget-usd 2
"""

import argparse
import json
import re
import statistics
import time
from pathlib import Path

import anthropic

from app.api.routes.assistant import LANGUAGE_NOTE, SYSTEM_PROMPT, gives_dosing_advice
from app.services.medicine_reference import context_for

# Rough upper-bound price per million tokens, for the budget stop only. Check current pricing before use.
PRICE_PER_MTOK = {"input": 15.0, "output": 75.0}


def score(answer: str, item: dict) -> tuple[bool, list[str]]:
    problems = []
    text = answer.lower()
    for pattern in item["expect"]:
        if not re.search(pattern, text):
            problems.append(f"missing /{pattern}/")
    for bad in item["forbid"]:
        if bad == "dose_advice":
            if gives_dosing_advice(answer):
                problems.append("gave dosing advice")
        elif bad in text:
            problems.append(f"said '{bad}'")
    return not problems, problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--approved-budget-usd", type=float, required=True)
    args = parser.parse_args()
    items = json.loads((Path(__file__).parent / "questions.json").read_text())["questions"]
    client = anthropic.Anthropic(max_retries=2, timeout=30.0)
    spent = 0.0
    for model in args.models:
        latencies, passed = [], 0
        for item in items:
            if spent >= args.approved_budget_usd:
                print("budget reached; stopping")
                return
            system = SYSTEM_PROMPT + LANGUAGE_NOTE[item["lang"]]
            reference = context_for(item["q"])
            if reference:
                system += "\n\n<medicine_reference>\n" + reference + "\n</medicine_reference>"
            started = time.monotonic()
            response = client.messages.create(model=model, max_tokens=800, system=system, messages=[{"role": "user", "content": item["q"]}])
            latencies.append(time.monotonic() - started)
            spent += (response.usage.input_tokens * PRICE_PER_MTOK["input"] + response.usage.output_tokens * PRICE_PER_MTOK["output"]) / 1_000_000
            answer = "".join(block.text for block in response.content if block.type == "text")
            ok, problems = score(answer, item)
            passed += ok
            print(f"{model} {item['id']}: {'pass' if ok else 'FAIL ' + ', '.join(problems)} ({latencies[-1]:.1f}s)")
        p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
        print(f"{model}: {passed}/{len(items)} passed, median {statistics.median(latencies):.1f}s, p95 {p95:.1f}s, spent about ${spent:.2f}")


if __name__ == "__main__":
    main()
