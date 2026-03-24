"""Tests for JUnit XML parser."""

from pathlib import Path

from flakydetector.models import TestOutcome
from flakydetector.parsers.junit_xml import JUnitXMLParser

FIXTURES = Path(__file__).parent / "fixtures"


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

    # ── Nested testsuites ────────────────────────────────────────

    def test_parse_nested_suites_count(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_nested_suites.xml", "run-1")
        assert summary.total == 4
        assert summary.passed == 3
        assert summary.failed == 1

    def test_parse_nested_suites_classnames(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_nested_suites.xml", "run-1")
        classnames = {r.classname for r in summary.results}
        assert "com.api.UserTest" in classnames
        assert "com.core.CacheTest" in classnames

    # ── system-out / system-err ──────────────────────────────────

    def test_parse_system_out_appended_to_stacktrace(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_system_out.xml", "run-1")
        failure = next(r for r in summary.results if r.outcome == TestOutcome.FAILED)
        assert failure.stacktrace is not None
        assert 'column "user_id" already exists' in failure.stacktrace

    def test_parse_passing_test_ignores_system_out(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_system_out.xml", "run-1")
        passed = next(r for r in summary.results if r.outcome == TestOutcome.PASSED)
        assert not passed.stacktrace

    # ── Maven Surefire rerun / flaky elements ────────────────────

    def test_parse_surefire_counts(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_surefire_rerun.xml", "run-1")
        assert summary.total == 3
        assert summary.passed == 2  # stable + flakyConnection (passed on rerun)
        assert summary.failed == 1  # hardFailure

    def test_parse_flaky_failure_detected(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_surefire_rerun.xml", "run-1")
        flaky = next(r for r in summary.results if r.name == "testFlakyConnection")
        assert flaky.outcome == TestOutcome.PASSED
        assert flaky.stacktrace is not None
        assert "Connection reset" in flaky.stacktrace

    def test_parse_rerun_failure_still_failed(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_surefire_rerun.xml", "run-1")
        hard = next(r for r in summary.results if r.name == "testHardFailure")
        assert hard.outcome == TestOutcome.FAILED
        assert hard.stacktrace is not None

    # ── Flat testcases under <testsuites> ────────────────────────

    def test_parse_flat_testcases_under_testsuites(self):
        parser = JUnitXMLParser()
        summary = parser.parse(FIXTURES / "junit_flat_testcases.xml", "run-1")
        assert summary.total == 3
        assert summary.failed == 1

    def test_can_parse_flat_testsuites(self):
        parser = JUnitXMLParser()
        assert parser.can_parse(FIXTURES / "junit_flat_testcases.xml")
