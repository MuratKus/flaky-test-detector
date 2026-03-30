"""Tests for reporters."""

import json

from flakydetector.models import FlakyTest, TrendPoint
from flakydetector.reporters import json_report, markdown


class TestReporters:
    def test_json_report_flaky(self):
        tests = [
            FlakyTest(
                test_name="C.testFlaky",
                total_runs=10,
                pass_count=5,
                fail_count=5,
                flakiness_rate=1.0,
                recommended_action="quarantine",
            )
        ]
        output = json_report.report_flaky(tests)
        data = json.loads(output)
        assert data["total_flaky"] == 1
        assert "C.testFlaky" in data["quarantine_recommended"]

    def test_markdown_report_flaky(self):
        tests = [
            FlakyTest(
                test_name="C.testFlaky",
                total_runs=10,
                pass_count=5,
                fail_count=5,
                flakiness_rate=1.0,
                recommended_action="quarantine",
            )
        ]
        output = markdown.report_flaky(tests)
        assert "Flaky Test Report" in output
        assert "C.testFlaky" in output
        assert "quarantine" in output

    def test_markdown_report_empty(self):
        output = markdown.report_flaky([])
        assert "No flaky tests detected" in output

    def test_markdown_report_includes_trend(self):
        tests = [
            FlakyTest(
                test_name="C.testFlaky",
                total_runs=6,
                pass_count=3,
                fail_count=3,
                flakiness_rate=1.0,
                recommended_action="quarantine",
                trend_direction="worsening",
            )
        ]
        output = markdown.report_flaky(tests)
        assert "Trend" in output
        assert "chart_with_downwards_trend" in output

    def test_json_report_includes_trend(self):
        trend = [
            TrendPoint(run_id="r1", outcome="passed", ingested_at="2025-01-01"),
            TrendPoint(run_id="r2", outcome="failed", ingested_at="2025-01-02"),
        ]
        tests = [
            FlakyTest(
                test_name="C.testFlaky",
                total_runs=2,
                pass_count=1,
                fail_count=1,
                flakiness_rate=1.0,
                recommended_action="quarantine",
                trend=trend,
                trend_direction="stable",
            )
        ]
        output = json_report.report_flaky(tests)
        data = json.loads(output)
        assert data["flaky_tests"][0]["trend_direction"] == "stable"
        assert len(data["flaky_tests"][0]["trend"]) == 2

    def test_markdown_report_includes_wasted_time(self):
        tests = [
            FlakyTest(
                test_name="C.testFlaky",
                total_runs=10,
                pass_count=5,
                fail_count=5,
                flakiness_rate=1.0,
                recommended_action="quarantine",
                wasted_time_sec=120.5,
            ),
            FlakyTest(
                test_name="C.testAnother",
                total_runs=8,
                pass_count=4,
                fail_count=4,
                flakiness_rate=1.0,
                recommended_action="investigate",
                wasted_time_sec=45.0,
            ),
        ]
        output = markdown.report_flaky(tests)
        assert "Wasted" in output
        assert "2.0m" in output  # 120.5s formatted
        assert "45.0s" in output
        assert "2.8m" in output  # total: 165.5s

    def test_markdown_report_no_wasted_time_when_zero(self):
        tests = [
            FlakyTest(
                test_name="C.testFlaky",
                total_runs=10,
                pass_count=5,
                fail_count=5,
                flakiness_rate=1.0,
                recommended_action="quarantine",
                wasted_time_sec=0.0,
            ),
        ]
        output = markdown.report_flaky(tests)
        # Should not have wasted time column when all are zero
        assert "Wasted" not in output
