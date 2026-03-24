"""Tests for flakiness analyzer."""

from flakydetector.analyzer import analyze
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
