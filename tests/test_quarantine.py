"""Tests for quarantine file export."""

from flakydetector.models import FlakyTest
from flakydetector.quarantine import export_json, export_junit, export_pytest


def _quarantined_tests():
    return [
        FlakyTest(
            test_name="com.example.LoginTest.testTimeout",
            total_runs=10,
            pass_count=5,
            fail_count=5,
            flakiness_rate=1.0,
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.example.CartTest.testCheckout",
            total_runs=8,
            pass_count=4,
            fail_count=4,
            flakiness_rate=1.0,
            recommended_action="quarantine",
        ),
    ]


def _mixed_tests():
    return [
        *_quarantined_tests(),
        FlakyTest(
            test_name="com.example.SearchTest.testQuery",
            total_runs=12,
            pass_count=10,
            fail_count=2,
            flakiness_rate=0.33,
            recommended_action="investigate",
        ),
        FlakyTest(
            test_name="com.example.HomeTest.testRender",
            total_runs=6,
            pass_count=5,
            fail_count=1,
            flakiness_rate=0.33,
            recommended_action="monitor",
        ),
    ]


class TestExportPytest:
    def test_generates_valid_python(self):
        output = export_pytest(_quarantined_tests())
        assert "import pytest" in output
        assert "pytest.mark.skip" in output

    def test_contains_test_names(self):
        output = export_pytest(_quarantined_tests())
        assert "com.example.LoginTest.testTimeout" in output
        assert "com.example.CartTest.testCheckout" in output

    def test_only_quarantined_by_default(self):
        output = export_pytest(_mixed_tests())
        assert "com.example.LoginTest.testTimeout" in output
        assert "com.example.SearchTest.testQuery" not in output

    def test_all_actions_when_requested(self):
        output = export_pytest(_mixed_tests(), actions=["quarantine", "investigate", "monitor"])
        assert "com.example.LoginTest.testTimeout" in output
        assert "com.example.SearchTest.testQuery" in output
        assert "com.example.HomeTest.testRender" in output

    def test_empty_list(self):
        output = export_pytest([])
        assert "QUARANTINED_TESTS = {" in output
        assert "QUARANTINED_TESTS = {\n}" in output  # empty set

    def test_contains_conftest_hook(self):
        output = export_pytest(_quarantined_tests())
        assert "pytest_collection_modifyitems" in output


class TestExportJunit:
    def test_generates_valid_xml(self):
        output = export_junit(_quarantined_tests())
        assert '<?xml version="1.0"' in output
        assert "<excludes>" in output

    def test_contains_test_patterns(self):
        output = export_junit(_quarantined_tests())
        # JUnit excludes are at class level
        assert "com.example.LoginTest" in output
        assert "com.example.CartTest" in output

    def test_only_quarantined_by_default(self):
        output = export_junit(_mixed_tests())
        assert "com.example.LoginTest" in output
        assert "com.example.SearchTest" not in output


class TestExportJson:
    def test_generates_valid_json(self):
        import json

        output = export_json(_quarantined_tests())
        data = json.loads(output)
        assert "quarantined_tests" in data
        assert len(data["quarantined_tests"]) == 2

    def test_includes_metadata(self):
        import json

        output = export_json(_quarantined_tests())
        data = json.loads(output)
        entry = data["quarantined_tests"][0]
        assert "test_name" in entry
        assert "flakiness_rate" in entry
        assert "reason" in entry

    def test_only_quarantined_by_default(self):
        import json

        output = export_json(_mixed_tests())
        data = json.loads(output)
        names = [t["test_name"] for t in data["quarantined_tests"]]
        assert "com.example.LoginTest.testTimeout" in names
        assert "com.example.SearchTest.testQuery" not in names
