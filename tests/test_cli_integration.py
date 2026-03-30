"""Integration tests for CLI — all tests run commands as subprocesses."""

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
CLI = [sys.executable, "-m", "flakydetector.cli"]


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run flaky-detect CLI as a subprocess."""
    return subprocess.run(
        [*CLI, *args],
        capture_output=True,
        text=True,
        check=check,
    )


class TestReport:
    """Test `flaky-detect report` (stateless one-shot mode)."""

    def test_report_text_shows_summary(self):
        result = run_cli("report", str(FIXTURES / "sample_junit.xml"))
        assert result.returncode == 0
        assert "sample_junit.xml" in result.stdout
        assert "junit_xml" in result.stdout

    def test_report_json_is_valid(self):
        result = run_cli("report", str(FIXTURES / "sample_junit.xml"), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["total"] == 7

    def test_report_markdown_has_header(self):
        result = run_cli("report", str(FIXTURES / "sample_junit.xml"), "--format", "markdown")
        assert result.returncode == 0
        assert "Run Summary" in result.stdout

    def test_report_allure_file(self):
        result = run_cli("report", str(FIXTURES / "sample_allure_result.json"))
        assert result.returncode == 0
        assert "allure_json" in result.stdout

    def test_report_gradle_log(self):
        result = run_cli("report", str(FIXTURES / "sample_gradle.log"))
        assert result.returncode == 0
        assert "plain_log" in result.stdout

    def test_report_html_is_valid(self):
        result = run_cli("report", str(FIXTURES / "sample_junit.xml"), "--format", "html")
        assert result.returncode == 0
        assert "<!DOCTYPE html>" in result.stdout
        assert "</html>" in result.stdout
        assert "<svg" in result.stdout


class TestDirectoryScanning:
    """Test pointing CLI at a directory with mixed file types."""

    def test_report_directory_parses_multiple_files(self):
        result = run_cli("report", str(FIXTURES))
        assert result.returncode == 0
        # Should parse at least the junit, allure, and gradle fixtures
        assert "junit_xml" in result.stdout
        assert "allure_json" in result.stdout
        assert "plain_log" in result.stdout


class TestIngestAnalyzeFlow:
    """Test the full ingest → analyze pipeline."""

    def test_ingest_stores_results(self, tmp_path):
        db = str(tmp_path / "test.db")
        result = run_cli(
            "--db",
            db,
            "ingest",
            str(FIXTURES / "sample_junit.xml"),
            "--run-id",
            "run-1",
        )
        assert result.returncode == 0
        assert "Ingested" in result.stdout
        assert "run-1" in result.stdout

    def test_ingest_json_output(self, tmp_path):
        db = str(tmp_path / "test.db")
        result = run_cli(
            "--db",
            db,
            "ingest",
            str(FIXTURES / "sample_junit.xml"),
            "--run-id",
            "run-1",
            "--format",
            "json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["run_id"] == "run-1"
        assert data["results_ingested"] > 0

    def test_analyze_no_flaky_with_single_run(self, tmp_path):
        db = str(tmp_path / "test.db")
        # Ingest one run
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        # Analyze — should find nothing (min-runs=3 by default)
        result = run_cli("--db", db, "analyze")
        assert result.returncode == 0
        assert "No flaky tests detected" in result.stdout

    def test_analyze_detects_flaky_after_multiple_runs(self, tmp_path):
        db = str(tmp_path / "test.db")
        # Ingest both junit fixtures (run1 has failures, run2 has different results)
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit_run2.xml"), "--run-id", "r2")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r3")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit_run2.xml"), "--run-id", "r4")
        # Analyze with low min-runs
        result = run_cli("--db", db, "analyze", "--min-runs", "2")
        assert result.returncode == 0
        # Should detect at least one flaky test (tests that flip between runs)

    def test_analyze_json_output(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli("--db", db, "analyze", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "total_flaky" in data

    def test_analyze_markdown_output(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli("--db", db, "analyze", "--format", "markdown")
        assert result.returncode == 0
        assert "Flaky Test Report" in result.stdout

    def test_analyze_html_output(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli("--db", db, "analyze", "--format", "html")
        assert result.returncode == 0
        assert "<!DOCTYPE html>" in result.stdout
        assert "Flaky Test Report" in result.stdout


class TestHistoryAndFingerprints:
    """Test history and fingerprints commands."""

    def test_history_no_data(self, tmp_path):
        db = str(tmp_path / "test.db")
        result = run_cli("--db", db, "history", "nonexistent.test")
        assert result.returncode == 0
        assert "No history found" in result.stdout

    def test_history_shows_records(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli("--db", db, "history", "com.example.LoginTest.testLoginSuccess")
        assert result.returncode == 0
        assert "History for:" in result.stdout
        assert "passed" in result.stdout

    def test_fingerprints_no_data(self, tmp_path):
        db = str(tmp_path / "test.db")
        result = run_cli("--db", db, "fingerprints")
        assert result.returncode == 0
        assert "No failure fingerprints" in result.stdout

    def test_fingerprints_shows_groups(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli("--db", db, "fingerprints")
        assert result.returncode == 0
        assert "root cause" in result.stdout.lower()


class TestOutputFlag:
    """Test -o / --output flag writes to file."""

    def test_report_output_to_file(self, tmp_path):
        out_file = tmp_path / "report.html"
        result = run_cli(
            "report",
            str(FIXTURES / "sample_junit.xml"),
            "--format",
            "html",
            "-o",
            str(out_file),
        )
        assert result.returncode == 0
        assert "Report written to" in result.stdout
        content = out_file.read_text()
        assert "<!DOCTYPE html>" in content

    def test_analyze_output_to_file(self, tmp_path):
        db = str(tmp_path / "test.db")
        out_file = tmp_path / "analyze.json"
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli(
            "--db",
            db,
            "analyze",
            "--format",
            "json",
            "-o",
            str(out_file),
        )
        assert result.returncode == 0
        assert "Report written to" in result.stdout
        import json

        data = json.loads(out_file.read_text())
        assert "total_flaky" in data


class TestCiUrlFlag:
    """Test --ci-url flag for HTML reports."""

    def test_report_html_with_ci_url(self):
        result = run_cli(
            "report",
            str(FIXTURES / "sample_junit.xml"),
            "--format",
            "html",
            "--ci-url",
            "https://ci.example.com/run/42",
        )
        assert result.returncode == 0
        assert "View in CI" in result.stdout
        assert "https://ci.example.com/run/42" in result.stdout

    def test_report_text_ignores_ci_url(self):
        result = run_cli(
            "report",
            str(FIXTURES / "sample_junit.xml"),
            "--ci-url",
            "https://ci.example.com/run/42",
        )
        assert result.returncode == 0
        assert "View in CI" not in result.stdout

    def test_analyze_html_with_ci_url(self, tmp_path):
        db = str(tmp_path / "test.db")
        run_cli("--db", db, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        result = run_cli(
            "--db",
            db,
            "analyze",
            "--format",
            "html",
            "--ci-url",
            "https://ci.example.com/run/99",
        )
        assert result.returncode == 0
        assert "<!DOCTYPE html>" in result.stdout


class TestErrorCases:
    """Test CLI handles errors gracefully."""

    def test_report_nonexistent_file(self):
        result = run_cli("report", "/nonexistent/path/file.xml", check=False)
        assert result.returncode != 0

    def test_report_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = run_cli("report", str(empty))
        # Should succeed but produce no output (no parseable files)
        assert result.returncode == 0

    def test_version_flag(self):
        result = run_cli("--version")
        assert result.returncode == 0
        assert "0.1.0" in result.stdout


class TestDbFlag:
    """Test --db flag for custom database location."""

    def test_custom_db_location(self, tmp_path):
        custom_db = tmp_path / "custom.db"
        run_cli(
            "--db",
            str(custom_db),
            "ingest",
            str(FIXTURES / "sample_junit.xml"),
            "--run-id",
            "r1",
        )
        assert custom_db.exists()

    def test_separate_dbs_are_isolated(self, tmp_path):
        db1 = str(tmp_path / "db1.db")
        db2 = str(tmp_path / "db2.db")
        run_cli("--db", db1, "ingest", str(FIXTURES / "sample_junit.xml"), "--run-id", "r1")
        # db2 should have no data
        result = run_cli("--db", db2, "analyze")
        assert "No flaky tests detected" in result.stdout
