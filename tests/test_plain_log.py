"""Tests for Plain Log parser."""

from pathlib import Path

from flakydetector.models import TestOutcome
from flakydetector.parsers.plain_log import PlainLogParser

FIXTURES = Path(__file__).parent / "fixtures"


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

    # ── ANSI color code stripping ────────────────────────────────

    def test_parse_ansi_colored_gradle_log(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_with_ansi.log", "run-1")
        assert summary.total == 3
        assert summary.passed == 2
        assert summary.failed == 1

    def test_can_parse_ansi_gradle_log(self):
        parser = PlainLogParser()
        assert parser.can_parse(FIXTURES / "log_with_ansi.log")

    # ── Gradle parameterized tests ───────────────────────────────

    def test_parse_gradle_parameterized_count(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_gradle_parameterized.log", "run-1")
        assert summary.total == 4
        assert summary.passed == 3
        assert summary.failed == 1

    def test_parse_gradle_parameterized_names(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_gradle_parameterized.log", "run-1")
        failed = [r for r in summary.results if r.outcome == TestOutcome.FAILED]
        assert len(failed) == 1
        assert "testLogin[Firefox]" in failed[0].name

    # ── Pytest parameterized tests ───────────────────────────────

    def test_parse_pytest_parameterized_count(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_pytest_parameterized.log", "run-1")
        assert summary.total == 4
        assert summary.failed == 1

    def test_parse_pytest_parameterized_name(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_pytest_parameterized.log", "run-1")
        failed = [r for r in summary.results if r.outcome == TestOutcome.FAILED]
        assert len(failed) == 1
        assert failed[0].name == "test_login[firefox-linux]"

    # ── Pytest === FAILURES === block ────────────────────────────

    def test_can_parse_pytest_failures_log(self):
        parser = PlainLogParser()
        assert parser.can_parse(FIXTURES / "log_pytest_failures.log")

    def test_parse_pytest_failures_count(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_pytest_failures.log", "run-1")
        assert summary.total == 5
        assert summary.passed == 3
        assert summary.failed == 2

    def test_parse_pytest_failures_has_stacktrace(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_pytest_failures.log", "run-1")
        conn_fail = next(r for r in summary.results if "test_connection" in r.name)
        assert conn_fail.stacktrace is not None
        assert "ConnectionError" in conn_fail.stacktrace

    def test_parse_pytest_failures_classnames(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_pytest_failures.log", "run-1")
        conn_fail = next(r for r in summary.results if "test_connection" in r.name)
        assert conn_fail.classname == "tests/test_api.py"

    # ── Maven Surefire log ───────────────────────────────────────

    def test_can_parse_maven_surefire_log(self):
        parser = PlainLogParser()
        assert parser.can_parse(FIXTURES / "log_maven_surefire.log")

    def test_parse_maven_surefire_counts(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_maven_surefire.log", "run-1")
        assert summary.total == 5
        assert summary.passed == 3
        assert summary.failed == 1
        assert summary.skipped == 1

    def test_parse_maven_surefire_failure_stacktrace(self):
        parser = PlainLogParser()
        summary = parser.parse(FIXTURES / "log_maven_surefire.log", "run-1")
        failed = [r for r in summary.results if r.outcome == TestOutcome.FAILED]
        assert len(failed) == 1
        assert failed[0].name == "testLoginTimeout"
        assert failed[0].stacktrace is not None
        assert "AssertionError" in failed[0].stacktrace
