"""Eval: does the persona check agree with human labels?

    python tests/evals/eval_persona.py          # rules only (free)
    python tests/evals/eval_persona.py --llm    # rules, then Claude for unclear titles

Reports accuracy on titles the checker decided, how many it left unclear, and every
disagreement. With PHOENIX_COLLECTOR_ENDPOINT set, each Claude call is traced in Phoenix.
Re-run after any playbook or prompt change; a drop in accuracy blocks the change.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bde_prospecting import llm, tracing  # noqa: E402
from bde_prospecting.checker import match_title  # noqa: E402
from bde_prospecting.config import load_config  # noqa: E402

DATASET = Path(__file__).with_name("persona_titles.csv")


def run(use_llm):
    cfg = load_config()
    results = []
    with open(DATASET, newline="") as f:
        for case in csv.DictReader(f):
            pb = cfg.playbooks[case["startup"]]
            persona = pb.personas[case["persona"]]
            verdict = match_title(case["title"], persona)
            source = "rules"
            if verdict == "unclear" and use_llm:
                try:
                    out = llm.classify_title(case["title"], persona, pb)
                    verdict = "match" if out["fits"] else "no_match"
                    source = "claude"
                except llm.Unavailable:
                    pass
            predicted = {"match": "fit", "no_match": "no_fit"}.get(verdict, "unclear")
            results.append({**case, "predicted": predicted, "source": source})
    return results


def report(results):
    decided = [r for r in results if r["predicted"] != "unclear"]
    correct = [r for r in decided if r["predicted"] == r["expected"]]
    false_fit = [r for r in decided if r["predicted"] == "fit" and r["expected"] == "no_fit"]
    accuracy = len(correct) / len(decided) if decided else 0.0
    print(f"cases: {len(results)}  decided: {len(decided)}  unclear (to human review): {len(results) - len(decided)}")
    print(f"accuracy on decided: {accuracy:.0%}  wrongly accepted: {len(false_fit)}")
    for r in results:
        if r["predicted"] not in ("unclear", r["expected"]):
            print(f"  WRONG  {r['startup']}/{r['persona']}: {r['title']!r} expected {r['expected']}, got {r['predicted']} ({r['source']})")
    for r in results:
        if r["predicted"] == "unclear":
            print(f"  unclear  {r['startup']}/{r['persona']}: {r['title']!r} (expected {r['expected']})")
    return accuracy, len(false_fit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()
    if args.llm and not llm.available():
        sys.exit("error: --llm needs ANTHROPIC_API_KEY and the anthropic package")
    tracing.setup()
    accuracy, false_fit = report(run(args.llm))
    sys.exit(0 if accuracy >= 0.95 and false_fit == 0 else 1)
