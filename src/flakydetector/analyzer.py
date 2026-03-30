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

from dataclasses import dataclass

from flakydetector.models import FlakyTest, TrendPoint
from flakydetector.store import Store

# Minimum runs needed before we can call a test flaky
MIN_RUNS_FOR_DETECTION = 3

# Flakiness threshold: above this, we flag the test
FLAKINESS_THRESHOLD = 0.2


@dataclass
class Thresholds:
    """Configurable thresholds for flakiness detection and action classification."""

    min_flakiness: float = FLAKINESS_THRESHOLD  # below this, test is not flagged
    quarantine: float = 0.5  # >= this → quarantine
    investigate: float = 0.3  # >= this → investigate
    # anything >= min_flakiness but below investigate → monitor


def analyze(
    store: Store, min_runs: int = MIN_RUNS_FOR_DETECTION, thresholds: Thresholds | None = None
) -> list[FlakyTest]:
    """Analyze all tests in the store and return flaky ones."""
    if thresholds is None:
        thresholds = Thresholds()

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

        if flakiness < thresholds.min_flakiness:
            continue

        # Collect distinct failure fingerprints
        fingerprints = list(
            {h["fingerprint"] for h in history if h["fingerprint"] and h["outcome"] != "passed"}
        )

        # Determine recommended action
        action = _recommend_action(flakiness, total, fingerprints, thresholds)

        # Build trend data
        trend_rows = store.get_test_trend(name, limit=100)
        trend = [
            TrendPoint(
                run_id=r["run_id"],
                outcome=r["outcome"],
                ingested_at=r.get("ingested_at", ""),
            )
            for r in trend_rows
        ]
        trend_dir = compute_trend_direction([r["outcome"] for r in trend_rows])

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
                trend=trend,
                trend_direction=trend_dir,
            )
        )

    # Sort by flakiness rate descending (worst offenders first)
    flaky_tests.sort(key=lambda t: t.flakiness_rate, reverse=True)
    return flaky_tests


def compute_trend_direction(outcomes: list[str]) -> str:
    """Compare pass rate of older half vs recent half to determine trend.

    Returns "improving", "worsening", "stable", or "" (not enough data).
    """
    if len(outcomes) < 2:
        return ""

    mid = len(outcomes) // 2
    older = outcomes[:mid]
    recent = outcomes[mid:]

    older_pass_rate = sum(1 for o in older if o == "passed") / len(older)
    recent_pass_rate = sum(1 for o in recent if o == "passed") / len(recent)

    diff = recent_pass_rate - older_pass_rate
    if diff > 0.1:
        return "improving"
    elif diff < -0.1:
        return "worsening"
    return "stable"


def _recommend_action(
    flakiness: float, total_runs: int, fingerprints: list[str], thresholds: Thresholds | None = None
) -> str:
    """Suggest what to do about a flaky test."""
    if thresholds is None:
        thresholds = Thresholds()

    if flakiness >= thresholds.quarantine:
        return "quarantine"
    elif flakiness >= thresholds.investigate:
        return "investigate"
    elif len(fingerprints) > 2:
        return "investigate"  # multiple distinct failure modes
    else:
        return "monitor"
