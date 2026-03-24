"""Flakiness analyzer.

Looks at test history across runs and identifies tests that flip between
pass and fail. A test that always passes or always fails is stable.
A test that sometimes passes and sometimes fails is flaky.

Flakiness rate: 1.0 - abs(pass_rate - 0.5) * 2
  - A test passing 50% of the time → flakiness 1.0 (maximally flaky)
  - A test passing 100% of the time → flakiness 0.0 (stable pass)
  - A test passing 0% of the time → flakiness 0.0 (stable fail)
  - A test passing 80% of the time → flakiness 0.4 (somewhat flaky)
"""

from flakydetector.models import FlakyTest
from flakydetector.store import Store

# Minimum runs needed before we can call a test flaky
MIN_RUNS_FOR_DETECTION = 3

# Flakiness threshold: above this, we flag the test
FLAKINESS_THRESHOLD = 0.2


def analyze(store: Store, min_runs: int = MIN_RUNS_FOR_DETECTION) -> list[FlakyTest]:
    """Analyze all tests in the store and return flaky ones."""
    flaky_tests = []
    test_names = store.get_all_test_names()

    for name in test_names:
        history = store.get_test_history(name, limit=100)
        if len(history) < min_runs:
            continue

        total = len(history)
        passes = sum(1 for h in history if h["outcome"] == "passed")
        fails = total - passes  # failed + error

        if total == 0:
            continue

        pass_rate = passes / total
        flakiness = 1.0 - abs(pass_rate - 0.5) * 2

        if flakiness < FLAKINESS_THRESHOLD:
            continue

        # Collect distinct failure fingerprints
        fingerprints = list(
            {h["fingerprint"] for h in history if h["fingerprint"] and h["outcome"] != "passed"}
        )

        # Determine recommended action
        action = _recommend_action(flakiness, total, fingerprints)

        flaky_tests.append(
            FlakyTest(
                test_name=name,
                total_runs=total,
                pass_count=passes,
                fail_count=fails,
                flakiness_rate=round(flakiness, 3),
                failure_fingerprints=fingerprints,
                last_seen=history[0].get("ingested_at", ""),
                recommended_action=action,
            )
        )

    # Sort by flakiness rate descending (worst offenders first)
    flaky_tests.sort(key=lambda t: t.flakiness_rate, reverse=True)
    return flaky_tests


def _recommend_action(flakiness: float, total_runs: int, fingerprints: list[str]) -> str:
    """Suggest what to do about a flaky test."""
    if flakiness >= 0.8:
        return "quarantine"  # extremely flaky, remove from blocking gates
    elif flakiness >= 0.5:
        return "quarantine"  # significantly flaky
    elif flakiness >= 0.3:
        return "investigate"  # moderately flaky, needs attention
    elif len(fingerprints) > 2:
        return "investigate"  # multiple distinct failure modes
    else:
        return "monitor"  # low flakiness, keep an eye on it
