"""Tests for flakiness analyzer."""

from flakydetector.analyzer import analyze, compute_trend_direction
from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.store import Store


class TestAnalyzer:
    def test_detects_flaky_test(self, tmp_path):
        store = Store(tmp_path / "test.db")

        for i in range(6):
            s = RunSummary(run_id=f"run-{i}", source="test")
            outcome = TestOutcome.PASSED if i % 2 == 0 else TestOutcome.FAILED
            s.add(
                TestResult(
                    name="testFlaky",
                    classname="C",
                    outcome=outcome,
                    stacktrace="err" if outcome == TestOutcome.FAILED else None,
                    fingerprint="fp1" if outcome == TestOutcome.FAILED else None,
                )
            )
            s.add(TestResult(name="testStable", classname="C", outcome=TestOutcome.PASSED))
            store.ingest(s)

        flaky = analyze(store, min_runs=3)
        flaky_names = [t.test_name for t in flaky]
        assert "C.testFlaky" in flaky_names
        assert "C.testStable" not in flaky_names

        ft = next(t for t in flaky if t.test_name == "C.testFlaky")
        assert ft.flakiness_rate == 1.0
        assert ft.recommended_action == "quarantine"
        store.close()

    def test_custom_thresholds(self, tmp_path):
        """Configurable thresholds change which tests get flagged and how."""
        store = Store(tmp_path / "test.db")

        # Create a test with 70% pass rate → flakiness = 1 - abs(0.7-0.5)*2 = 0.6
        for i in range(10):
            s = RunSummary(run_id=f"run-{i}", source="test")
            outcome = TestOutcome.PASSED if i < 7 else TestOutcome.FAILED
            s.add(
                TestResult(
                    name="testMedium",
                    classname="C",
                    outcome=outcome,
                    fingerprint="fp1" if outcome == TestOutcome.FAILED else None,
                )
            )
            store.ingest(s)

        # Default threshold (0.2) should flag it
        flaky = analyze(store, min_runs=3)
        assert len(flaky) == 1

        # High threshold should exclude it
        from flakydetector.analyzer import Thresholds

        strict = Thresholds(min_flakiness=0.8)
        flaky = analyze(store, min_runs=3, thresholds=strict)
        assert len(flaky) == 0

        # Custom action thresholds: 0.6 is now "monitor" instead of "quarantine"
        custom = Thresholds(quarantine=0.9, investigate=0.7)
        flaky = analyze(store, min_runs=3, thresholds=custom)
        assert len(flaky) == 1
        assert flaky[0].recommended_action == "monitor"

        store.close()

    def test_thresholds_from_defaults(self):
        """Thresholds class has sensible defaults matching current behavior."""
        from flakydetector.analyzer import Thresholds

        t = Thresholds()
        assert t.min_flakiness == 0.2
        assert t.quarantine == 0.5
        assert t.investigate == 0.3

    def test_no_flaky_when_always_fails(self, tmp_path):
        store = Store(tmp_path / "test.db")
        for i in range(5):
            s = RunSummary(run_id=f"run-{i}", source="test")
            s.add(
                TestResult(
                    name="testBroken", classname="C", outcome=TestOutcome.FAILED, fingerprint="fp1"
                )
            )
            store.ingest(s)

        flaky = analyze(store, min_runs=3)
        assert len(flaky) == 0
        store.close()

    def test_flaky_test_has_trend_data(self, tmp_path):
        """Analyzed flaky tests should include trend data."""
        store = Store(tmp_path / "test.db")
        for i in range(6):
            s = RunSummary(run_id=f"run-{i}", source="test")
            outcome = TestOutcome.PASSED if i % 2 == 0 else TestOutcome.FAILED
            s.add(
                TestResult(
                    name="testFlaky",
                    classname="C",
                    outcome=outcome,
                    fingerprint="fp1" if outcome == TestOutcome.FAILED else None,
                )
            )
            store.ingest(s)

        flaky = analyze(store, min_runs=3)
        ft = flaky[0]
        assert len(ft.trend) == 6
        assert ft.trend[0].run_id == "run-0"
        assert ft.trend[0].outcome == "passed"
        assert ft.trend_direction != ""
        store.close()

    def test_flaky_test_has_wasted_time(self, tmp_path):
        """Analyzed flaky tests should include wasted CI time."""
        store = Store(tmp_path / "test.db")
        for i in range(6):
            s = RunSummary(run_id=f"run-{i}", source="test")
            outcome = TestOutcome.PASSED if i % 2 == 0 else TestOutcome.FAILED
            s.add(
                TestResult(
                    name="testFlaky",
                    classname="C",
                    outcome=outcome,
                    duration_sec=10.0,
                    fingerprint="fp1" if outcome == TestOutcome.FAILED else None,
                )
            )
            store.ingest(s)

        flaky = analyze(store, min_runs=3)
        ft = flaky[0]
        # 3 failed runs * 10s each = 30s wasted
        assert ft.wasted_time_sec == 30.0
        store.close()


class TestTrendDirection:
    """Test compute_trend_direction in isolation."""

    def test_improving_trend(self):
        # Older half: mostly failing. Recent half: mostly passing.
        outcomes = ["failed", "failed", "failed", "passed", "passed", "passed"]
        assert compute_trend_direction(outcomes) == "improving"

    def test_worsening_trend(self):
        # Older half: mostly passing. Recent half: mostly failing.
        outcomes = ["passed", "passed", "passed", "failed", "failed", "failed"]
        assert compute_trend_direction(outcomes) == "worsening"

    def test_stable_trend(self):
        # Both halves have same pass rate (50/50 each).
        outcomes = ["passed", "failed", "passed", "failed"]
        assert compute_trend_direction(outcomes) == "stable"

    def test_too_few_runs(self):
        # Not enough data to determine trend.
        assert compute_trend_direction(["passed"]) == ""
        assert compute_trend_direction([]) == ""
