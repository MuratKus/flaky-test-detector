#!/usr/bin/env python
"""Eval script for the AI investigator.

Runs against synthetic fixtures and scores category correctness,
confidence calibration, and evidence integrity.

Usage:
    uv run python tests/eval_investigator.py

Requires ANTHROPIC_API_KEY in environment. Costs tokens.
Pass thresholds: 80% synthetic, 100% negatives.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.fixtures.investigator.fixtures import ALL_FIXTURES
from flakydetector.investigator import investigate


def score_result(result, label: dict) -> dict:
    category_ok = result.category == label["category"]
    expected_conf = label["confidence"]
    if expected_conf == "high":
        confidence_ok = result.confidence == "high"
    elif expected_conf == "medium":
        confidence_ok = result.confidence in ("medium", "high")
    else:
        confidence_ok = True

    evidence_ok = len(result.evidence) > 0 and all(
        "source" in e and e["source"] in ("SQLite", "git", "source")
        for e in result.evidence
    )

    return {
        "category_ok": category_ok,
        "confidence_ok": confidence_ok,
        "evidence_ok": evidence_ok,
        "category_got": result.category,
        "category_expected": label["category"],
        "confidence_got": result.confidence,
    }


def main():
    print("AI Investigator Eval\n" + "=" * 40)
    results = []

    for name, factory in ALL_FIXTURES:
        store, test_name, label = factory()
        print(f"\n[{name}] investigating '{test_name}'...")
        try:
            result = investigate(test_name, store, use_cache=False)
            scores = score_result(result, label)
            status = "PASS" if scores["category_ok"] else "FAIL"
            print(f"  {status}: expected={label['category']} got={result.category} "
                  f"confidence={result.confidence}")
            results.append({"name": name, "label": label, **scores})
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"name": name, "label": label, "category_ok": False,
                            "confidence_ok": False, "evidence_ok": False, "error": str(e)})
        finally:
            store.close()

    print("\n" + "=" * 40)
    total = len(results)
    cat_pass = sum(1 for r in results if r.get("category_ok"))
    conf_pass = sum(1 for r in results if r.get("confidence_ok"))
    ev_pass = sum(1 for r in results if r.get("evidence_ok"))

    negative_names = {"negative_consistently_failing", "negative_stable_pass"}
    negative_results = [r for r in results if r["name"] in negative_names]
    synthetic_results = [r for r in results if r["name"] not in negative_names]

    neg_cat_pass = sum(1 for r in negative_results if r.get("category_ok"))
    syn_cat_pass = sum(1 for r in synthetic_results if r.get("category_ok"))

    print(f"Category correct:      {cat_pass}/{total}")
    print(f"  Synthetic:           {syn_cat_pass}/{len(synthetic_results)} (threshold: 80%)")
    print(f"  Negatives:           {neg_cat_pass}/{len(negative_results)} (threshold: 100%)")
    print(f"Confidence calibrated: {conf_pass}/{total}")
    print(f"Evidence integrity:    {ev_pass}/{total}")

    syn_pct = syn_cat_pass / len(synthetic_results) if synthetic_results else 0
    neg_pct = neg_cat_pass / len(negative_results) if negative_results else 0

    passed = syn_pct >= 0.80 and neg_pct >= 1.0
    print(f"\n{'EVAL PASSED' if passed else 'EVAL FAILED'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
