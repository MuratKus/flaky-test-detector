"""Tests for flaky-test-detector."""

import json
import tempfile
from pathlib import Path

import pytest

from flakydetector.analyzer import analyze
from flakydetector.fingerprint import fingerprint, fingerprint_results, normalize_stacktrace
from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.parsers.allure_json import AllureJSONParser
from flakydetector.parsers.junit_xml import JUnitXMLParser
from flakydetector.parsers.plain_log import PlainLogParser
from flakydetector.reporters import json_report, markdown
from flakydetector.store import Store

FIXTURES = Path(__file__).parent / "fixtures"


# ── JUnit XML Parser ──────────────────────────────────────────────

class TestJUnitXMLParser:
    def test_can_parse_valid_xml(self):
        parser = JUnitXMLParser()
        assert parser.can_parse(FIXTURES / "sample_junit.xml")

    def test_can_parse_rejects_json(self):
        parser = JUnitXMLParser()
        assert not parser.can_parse(FIXTURES / "sample_allure_result.json")

    def test_parse_counts(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "sample_junit.xml", "run-1")
        assert summary.total == 7
        assert summary.passed == 3
        assert summary.failed == 2
        assert summary.errored == 1
        assert summary.skipped == 1

    def test_parse_failure_has_stacktrace(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "sample_junit.xml", "run-1")
        failures = [r for r in summary.results if r.outcome == TestOutcome.FAILED]
        assert len(failures) == 2
        assert all(r.stacktrace for r in failures)

    def test_parse_classnames(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "sample_junit.xml", "run-1")
        classnames = {r.classname for r in summary.results}
        assert "com.example.LoginTest" in classnames
        assert "com.example.CartTest" in classnames


# ── Allure JSON Parser ────────────────────────────────────────────

class TestAllureJSONParser:
    def test_can_parse_allure_file(self):
        parser = AllureJSONParser()
        assert parser.can_parse(FIXTURES / "sample_allure_result.json")

    def test_parse_single_result(self):
        parser = AllureJSONParser()
        summary = parser.parse(FIXTURES / "sample_allure_result.json", "run-1")
        assert summary.total == 1
        assert summary.failed == 1
        r = summary.results[0]
        assert r.name == "testSearchResults"
        assert "Expected 10 results" in r.error_message

    def test_can_parse_rejects_non_allure_json(self):
        parser = AllureJSONParser()
        # A plain JSON without 'status' and 'name' fields
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"foo": "bar"}, f)
            f.flush()
            assert not parser.can_parse(Path(f.name))


# ── Plain Log Parser ──────────────────────────────────────────────

class TestPlainLogParser:
    def test_can_parse_gradle_log(self):
        parser = PlainLogParser()
        assert parser.can_parse(FIXTURES / "sample_gradle.log")

    def test_parse_gradle_counts(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "sample_gradle.log", "run-1")
        assert summary.passed == 2
        assert summary.failed == 2
        assert summary.skipped == 1

    def test_can_parse_rejects_xml(self):
        parser = PlainLogParser()
        assert not parser.can_parse(FIXTURES / "sample_junit.xml")


# ── Fingerprinting ────────────────────────────────────────────────

class TestFingerprinting:
    def test_same_trace_different_line_numbers(self):
        trace1 = "java.lang.NullPointerException\n\tat com.Foo.bar(Foo.java:42)"
        trace2 = "java.lang.NullPointerException\n\tat com.Foo.bar(Foo.java:99)"
        assert fingerprint(trace1) == fingerprint(trace2)

    def test_different_exceptions_different_fingerprint(self):
        trace1 = "java.lang.NullPointerException\n\tat com.Foo.bar(Foo.java:42)"
        trace2 = "java.lang.IllegalStateException\n\tat com.Baz.qux(Baz.java:42)"
        assert fingerprint(trace1) != fingerprint(trace2)

    def test_normalizes_timestamps(self):
        t = normalize_stacktrace("Error at 2024-01-15T10:30:00Z in module")
        assert "2024-01-15" not in t
        assert "TIMESTAMP" in t

    def test_normalizes_uuids(self):
        t = normalize_stacktrace("Session a1b2c3d4-e5f6-7890-abcd-ef1234567890 failed")
        assert "a1b2c3d4" not in t
        assert "UUID" in t

    def test_empty_input(self):
        assert fingerprint(None) == ""
        assert fingerprint("") == ""
        assert fingerprint("   ") == ""

    def test_fingerprint_results_adds_fingerprints(self):
        results = [
            TestResult(name="t1", classname="C", outcome=TestOutcome.FAILED,
                       stacktrace="java.lang.Error\n\tat X.y(X.java:1)"),
            TestResult(name="t2", classname="C", outcome=TestOutcome.PASSED),
        ]
        fingerprint_results(results)
        assert results[0].fingerprint  # has a fingerprint
        assert results[1].fingerprint is None  # no stacktrace, no fingerprint


# ── Store ─────────────────────────────────────────────────────────

class TestStore:
    def _make_store(self, tmp_path):
        return Store(tmp_path / "test.db")

    def test_ingest_and_retrieve(self, tmp_path):
        store = self._make_store(tmp_path)
        summary = RunSummary(run_id="r1", source="junit_xml")
        summary.add(TestResult(name="testA", classname="C", outcome=TestOutcome.PASSED))
        summary.add(TestResult(name="testB", classname="C", outcome=TestOutcome.FAILED,
                               stacktrace="err", fingerprint="fp123"))
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


# ── Analyzer ──────────────────────────────────────────────────────

class TestAnalyzer:
    def test_detects_flaky_test(self, tmp_path):
        store = Store(tmp_path / "test.db")

        # Simulate a test that flips between pass and fail across 6 runs
        for i in range(6):
            s = RunSummary(run_id=f"run-{i}", source="test")
            outcome = TestOutcome.PASSED if i % 2 == 0 else TestOutcome.FAILED
            s.add(TestResult(
                name="testFlaky", classname="C", outcome=outcome,
                stacktrace="err" if outcome == TestOutcome.FAILED else None,
                fingerprint="fp1" if outcome == TestOutcome.FAILED else None,
            ))
            # A stable test for comparison
            s.add(TestResult(name="testStable", classname="C", outcome=TestOutcome.PASSED))
            store.ingest(s)

        flaky = analyze(store, min_runs=3)
        flaky_names = [t.test_name for t in flaky]
        assert "C.testFlaky" in flaky_names
        assert "C.testStable" not in flaky_names

        # Check the flaky test details
        ft = next(t for t in flaky if t.test_name == "C.testFlaky")
        assert ft.flakiness_rate == 1.0  # 50/50 split = max flakiness
        assert ft.recommended_action == "quarantine"
        store.close()

    def test_no_flaky_when_always_fails(self, tmp_path):
        store = Store(tmp_path / "test.db")
        for i in range(5):
            s = RunSummary(run_id=f"run-{i}", source="test")
            s.add(TestResult(name="testBroken", classname="C", outcome=TestOutcome.FAILED,
                             fingerprint="fp1"))
            store.ingest(s)

        flaky = analyze(store, min_runs=3)
        assert len(flaky) == 0  # always fails = not flaky, just broken
        store.close()


# ── Reporters ─────────────────────────────────────────────────────

class TestReporters:
    def test_json_report_flaky(self):
        from flakydetector.models import FlakyTest
        tests = [FlakyTest(
            test_name="C.testFlaky", total_runs=10, pass_count=5,
            fail_count=5, flakiness_rate=1.0,
            recommended_action="quarantine",
        )]
        output = json_report.report_flaky(tests)
        data = json.loads(output)
        assert data["total_flaky"] == 1
        assert "C.testFlaky" in data["quarantine_recommended"]

    def test_markdown_report_flaky(self):
        from flakydetector.models import FlakyTest
        tests = [FlakyTest(
            test_name="C.testFlaky", total_runs=10, pass_count=5,
            fail_count=5, flakiness_rate=1.0,
            recommended_action="quarantine",
        )]
        output = markdown.report_flaky(tests)
        assert "Flaky Test Report" in output
        assert "C.testFlaky" in output
        assert "quarantine" in output

    def test_markdown_report_empty(self):
        output = markdown.report_flaky([])
        assert "No flaky tests detected" in output
