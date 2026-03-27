"""Tests for HTML reporter."""

import re

from flakydetector.models import FlakyTest, RunSummary, TestOutcome, TestResult
from flakydetector.reporters import html_report


def _make_flaky_tests():
    """Shared fixture: a list of FlakyTest instances with varied actions."""
    return [
        FlakyTest(
            test_name="com.example.LoginTest.testFlaky",
            total_runs=10,
            pass_count=5,
            fail_count=5,
            flakiness_rate=1.0,
            failure_fingerprints=["abc123"],
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.example.CartTest.testAddItem",
            total_runs=8,
            pass_count=6,
            fail_count=2,
            flakiness_rate=0.5,
            failure_fingerprints=["def456", "ghi789"],
            recommended_action="investigate",
        ),
        FlakyTest(
            test_name="com.example.SearchTest.testQuery",
            total_runs=12,
            pass_count=10,
            fail_count=2,
            flakiness_rate=0.33,
            failure_fingerprints=["jkl012"],
            recommended_action="monitor",
        ),
    ]


def _make_run_summary():
    """Shared fixture: a RunSummary with mixed outcomes and failures."""
    summary = RunSummary(run_id="run-42", source="junit_xml")
    summary.add(
        TestResult(
            name="testLogin",
            classname="LoginTest",
            outcome=TestOutcome.PASSED,
            duration_sec=1.2,
        )
    )
    summary.add(
        TestResult(
            name="testLogout",
            classname="LoginTest",
            outcome=TestOutcome.PASSED,
            duration_sec=0.5,
        )
    )
    summary.add(
        TestResult(
            name="testAddItem",
            classname="CartTest",
            outcome=TestOutcome.FAILED,
            duration_sec=2.3,
            error_message="AssertionError: expected 3 items",
            stacktrace="at CartTest.testAddItem(CartTest.java:42)",
            fingerprint="fp_aaa",
        )
    )
    summary.add(
        TestResult(
            name="testRemoveItem",
            classname="CartTest",
            outcome=TestOutcome.FAILED,
            duration_sec=1.1,
            error_message="NullPointerException",
            stacktrace="at CartTest.testRemoveItem(CartTest.java:88)",
            fingerprint="fp_aaa",
        )
    )
    summary.add(
        TestResult(
            name="testSearch",
            classname="SearchTest",
            outcome=TestOutcome.ERROR,
            duration_sec=5.0,
            error_message="TimeoutException",
            stacktrace="at SearchTest.testSearch(SearchTest.java:15)",
            fingerprint="fp_bbb",
        )
    )
    summary.add(
        TestResult(
            name="testSkipped",
            classname="SkipTest",
            outcome=TestOutcome.SKIPPED,
        )
    )
    return summary


class TestHtmlReportFlaky:
    def test_returns_valid_html(self):
        output = html_report.report_flaky(_make_flaky_tests())
        assert output.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in output

    def test_contains_title(self):
        output = html_report.report_flaky(_make_flaky_tests())
        assert "Flaky Test Report" in output

    def test_empty_list(self):
        output = html_report.report_flaky([])
        assert "<!DOCTYPE html>" in output
        assert "No flaky tests detected" in output

    def test_shows_test_names(self):
        tests = _make_flaky_tests()
        output = html_report.report_flaky(tests)
        for t in tests:
            assert t.test_name in output

    def test_shows_flakiness_rates(self):
        output = html_report.report_flaky(_make_flaky_tests())
        assert "100" in output  # 1.0 * 100 = 100%
        assert "50" in output  # 0.5 * 100 = 50%
        assert "33" in output  # 0.33 * 100 = 33%

    def test_shows_recommended_actions(self):
        output = html_report.report_flaky(_make_flaky_tests())
        assert "quarantine" in output.lower()
        assert "investigate" in output.lower()
        assert "monitor" in output.lower()

    def test_contains_svg_chart(self):
        output = html_report.report_flaky(_make_flaky_tests())
        assert "<svg" in output

    def test_no_external_resources(self):
        output = html_report.report_flaky(_make_flaky_tests())
        # No external script or link tags
        assert not re.search(r'<script[^>]+src=["\']https?://', output)
        assert not re.search(r'<link[^>]+href=["\']https?://', output)

    def test_escapes_html_in_test_names(self):
        tests = [
            FlakyTest(
                test_name='<script>alert("xss")</script>',
                total_runs=10,
                pass_count=5,
                fail_count=5,
                flakiness_rate=1.0,
                recommended_action="quarantine",
            )
        ]
        output = html_report.report_flaky(tests)
        assert "<script>alert" not in output
        assert "&lt;script&gt;" in output


class TestHtmlReportRun:
    def test_returns_valid_html(self):
        output = html_report.report_run(_make_run_summary())
        assert output.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in output

    def test_shows_run_id(self):
        output = html_report.report_run(_make_run_summary())
        assert "run-42" in output

    def test_shows_counts(self):
        summary = _make_run_summary()
        output = html_report.report_run(summary)
        # Total 6, Passed 2, Failed 2, Errors 1, Skipped 1
        assert ">6<" in output or ">6 " in output or " 6<" in output
        assert "2" in output  # passed and failed counts

    def test_shows_failures_grouped_by_fingerprint(self):
        output = html_report.report_run(_make_run_summary())
        assert "fp_aaa" in output
        assert "fp_bbb" in output

    def test_contains_svg_donut(self):
        output = html_report.report_run(_make_run_summary())
        assert "<svg" in output

    def test_escapes_error_messages(self):
        summary = RunSummary(run_id="run-99", source="junit_xml")
        summary.add(
            TestResult(
                name="testXss",
                classname="XssTest",
                outcome=TestOutcome.FAILED,
                error_message='Expected <div class="foo"> but got <span>',
                fingerprint="fp_xss",
            )
        )
        output = html_report.report_run(summary)
        assert '<div class="foo">' not in output
        assert "&lt;div" in output

    def test_no_failures_section_when_all_pass(self):
        summary = RunSummary(run_id="run-clean", source="junit_xml")
        summary.add(
            TestResult(
                name="testOk",
                classname="OkTest",
                outcome=TestOutcome.PASSED,
            )
        )
        output = html_report.report_run(summary)
        assert "<!DOCTYPE html>" in output
        # Should not contain failure-related sections
        assert "Failures" not in output or "0 failures" in output.lower()
