"""Tests for SQLite store."""

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.store import Store


class TestStore:
    def _make_store(self, tmp_path):
        return Store(tmp_path / "test.db")

    def test_ingest_and_retrieve(self, tmp_path):
        store = self._make_store(tmp_path)
        summary = RunSummary(run_id="r1", source="junit_xml")
        summary.add(TestResult(name="testA", classname="C", outcome=TestOutcome.PASSED))
        summary.add(
            TestResult(
                name="testB",
                classname="C",
                outcome=TestOutcome.FAILED,
                stacktrace="err",
                fingerprint="fp123",
            )
        )
        store.ingest(summary)

        names = store.get_all_test_names()
        assert "C.testA" in names
        assert "C.testB" in names

        history = store.get_test_history("C.testB")
        assert len(history) == 1
        assert history[0]["outcome"] == "failed"
        store.close()

    def test_run_count(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(3):
            s = RunSummary(run_id=f"r{i}", source="test")
            s.add(TestResult(name="t", classname="C", outcome=TestOutcome.PASSED))
            store.ingest(s)
        assert store.get_run_count() == 3
        store.close()

    def test_get_test_trend(self, tmp_path):
        store = self._make_store(tmp_path)
        outcomes = ["passed", "failed", "passed", "failed", "passed"]
        for i, outcome in enumerate(outcomes):
            s = RunSummary(run_id=f"r{i}", source="test")
            s.add(
                TestResult(
                    name="testFlaky",
                    classname="C",
                    outcome=TestOutcome(outcome),
                )
            )
            store.ingest(s)

        trend = store.get_test_trend("C.testFlaky")
        assert len(trend) == 5
        # Should be ordered oldest → newest
        assert trend[0]["run_id"] == "r0"
        assert trend[-1]["run_id"] == "r4"
        # Should have outcome field
        assert trend[0]["outcome"] == "passed"
        assert trend[1]["outcome"] == "failed"
        store.close()

    def test_get_test_trend_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        trend = store.get_test_trend("nonexistent")
        assert trend == []
        store.close()

    def test_get_wasted_duration(self, tmp_path):
        store = self._make_store(tmp_path)
        # Run 1: test passes in 2s
        s1 = RunSummary(run_id="r1", source="test")
        s1.add(
            TestResult(
                name="testFlaky", classname="C", outcome=TestOutcome.PASSED, duration_sec=2.0
            )
        )
        store.ingest(s1)
        # Run 2: test fails in 3s
        s2 = RunSummary(run_id="r2", source="test")
        s2.add(
            TestResult(
                name="testFlaky", classname="C", outcome=TestOutcome.FAILED, duration_sec=3.0
            )
        )
        store.ingest(s2)
        # Run 3: test fails in 4s
        s3 = RunSummary(run_id="r3", source="test")
        s3.add(
            TestResult(
                name="testFlaky", classname="C", outcome=TestOutcome.FAILED, duration_sec=4.0
            )
        )
        store.ingest(s3)

        wasted = store.get_wasted_duration("C.testFlaky")
        # Only failed runs count: 3.0 + 4.0 = 7.0
        assert wasted == 7.0
        store.close()

    def test_get_wasted_duration_no_failures(self, tmp_path):
        store = self._make_store(tmp_path)
        s = RunSummary(run_id="r1", source="test")
        s.add(
            TestResult(name="testOk", classname="C", outcome=TestOutcome.PASSED, duration_sec=5.0)
        )
        store.ingest(s)

        assert store.get_wasted_duration("C.testOk") == 0.0
        store.close()
