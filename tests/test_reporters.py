"""Tests for reporters."""

import json

from flakydetector.models import FlakyTest
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
