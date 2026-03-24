"""JSON reporter — structured output for piping to other tools."""

import json
from dataclasses import asdict

from flakydetector.models import FlakyTest, RunSummary


def report_flaky(flaky_tests: list[FlakyTest]) -> str:
    """Generate JSON report of flaky tests."""
    data = {
        "flaky_tests": [asdict(t) for t in flaky_tests],
        "total_flaky": len(flaky_tests),
        "quarantine_recommended": [
            t.test_name for t in flaky_tests if t.recommended_action == "quarantine"
        ],
        "investigate_recommended": [
            t.test_name for t in flaky_tests if t.recommended_action == "investigate"
        ],
    }
    return json.dumps(data, indent=2)


def report_run(summary: RunSummary) -> str:
    """Generate JSON summary of a single run."""
    failures = [
        {
            "test": r.fqn,
            "error": r.error_message,
            "fingerprint": r.fingerprint or "",
        }
        for r in summary.results
        if r.outcome.value in ("failed", "error")
    ]

    data = {
        "run_id": summary.run_id,
        "source": summary.source,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "errored": summary.errored,
        "skipped": summary.skipped,
        "failures": failures,
        "unique_failure_fingerprints": len({f["fingerprint"] for f in failures if f["fingerprint"]}),
    }
    return json.dumps(data, indent=2)
