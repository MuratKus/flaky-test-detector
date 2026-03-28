"""Tests for the GitHub Action wrapper."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
CLI = [sys.executable, "-m", "flakydetector.cli"]
ENTRYPOINT = REPO_ROOT / "action" / "entrypoint.py"


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([*CLI, *args], capture_output=True, text=True, check=check)


def run_entrypoint(env_overrides: dict) -> subprocess.CompletedProcess:
    """Run the action entrypoint with custom environment variables."""
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class TestActionYml:
    """Validate action.yml structure."""

    def test_action_yml_exists(self):
        assert (REPO_ROOT / "action.yml").is_file()

    def test_action_yml_valid_yaml(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert isinstance(data, dict)

    def test_has_required_fields(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert "name" in data
        assert "description" in data
        assert "inputs" in data
        assert "runs" in data

    def test_path_input_required(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert "path" in data["inputs"]
        assert data["inputs"]["path"]["required"] is True

    def test_composite_type(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert data["runs"]["using"] == "composite"

    def test_has_report_output(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert "outputs" in data
        assert "report" in data["outputs"]

    def test_has_mode_input_with_default(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert "mode" in data["inputs"]
        assert data["inputs"]["mode"]["default"] == "report"

    def test_has_comment_on_pr_input(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert "comment-on-pr" in data["inputs"]

    def test_has_branding(self):
        data = yaml.safe_load((REPO_ROOT / "action.yml").read_text())
        assert "branding" in data


class TestEntrypoint:
    """Test the action entrypoint script."""

    def test_entrypoint_exists(self):
        assert ENTRYPOINT.is_file()

    def test_report_mode_writes_summary(self, tmp_path):
        """Report mode produces markdown and writes to step summary."""
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        result = run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES / "sample_junit.xml"),
                "INPUT_MODE": "report",
                "INPUT_RUN_ID": "",
                "INPUT_DB_PATH": str(tmp_path / "test.db"),
                "INPUT_MIN_RUNS": "3",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )
        assert result.returncode == 0

        # Step summary should have markdown
        summary = summary_file.read_text()
        assert "Test Run Summary" in summary

    def test_report_mode_sets_outputs(self, tmp_path):
        """Report mode writes report and total_tests to GITHUB_OUTPUT."""
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES / "sample_junit.xml"),
                "INPUT_MODE": "report",
                "INPUT_RUN_ID": "",
                "INPUT_DB_PATH": str(tmp_path / "test.db"),
                "INPUT_MIN_RUNS": "3",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )

        content = output_file.read_text()
        assert "report<<EOF" in content
        assert "total_tests=" in content

    def test_report_mode_generates_html_artifact(self, tmp_path):
        """Report mode writes an HTML file for artifact upload."""
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        html_path = tmp_path / "report.html"
        output_file.touch()
        summary_file.touch()

        run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES / "sample_junit.xml"),
                "INPUT_MODE": "report",
                "INPUT_RUN_ID": "",
                "INPUT_DB_PATH": str(tmp_path / "test.db"),
                "INPUT_MIN_RUNS": "3",
                "INPUT_HTML_REPORT_PATH": str(html_path),
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )

        assert html_path.exists()
        html_content = html_path.read_text()
        assert "<!DOCTYPE html>" in html_content
        assert "html_report_path=" in output_file.read_text()

    def test_analyze_mode(self, tmp_path):
        """Analyze mode ingests then reports flakiness."""
        db = str(tmp_path / "test.db")
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        result = run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES / "sample_junit.xml"),
                "INPUT_MODE": "analyze",
                "INPUT_RUN_ID": "action-run-1",
                "INPUT_DB_PATH": db,
                "INPUT_MIN_RUNS": "3",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )
        assert result.returncode == 0

        content = output_file.read_text()
        assert "report<<EOF" in content
        assert "Flaky Test Report" in content

    def test_analyze_mode_sets_flaky_count(self, tmp_path):
        """Analyze mode writes flaky_count to GITHUB_OUTPUT."""
        db = str(tmp_path / "test.db")
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES / "sample_junit.xml"),
                "INPUT_MODE": "analyze",
                "INPUT_RUN_ID": "run-1",
                "INPUT_DB_PATH": db,
                "INPUT_MIN_RUNS": "3",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )

        content = output_file.read_text()
        assert "flaky_count=" in content

    def test_missing_path_fails(self, tmp_path):
        """Entrypoint fails when path input is missing."""
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        result = run_entrypoint(
            {
                "INPUT_PATH": "",
                "INPUT_MODE": "report",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )
        assert result.returncode != 0

    def test_invalid_mode_fails(self, tmp_path):
        """Entrypoint fails with unknown mode."""
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        result = run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES / "sample_junit.xml"),
                "INPUT_MODE": "invalid",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )
        assert result.returncode != 0

    def test_directory_report_mode(self, tmp_path):
        """Report mode works with a directory of mixed fixtures."""
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.touch()
        summary_file.touch()

        result = run_entrypoint(
            {
                "INPUT_PATH": str(FIXTURES),
                "INPUT_MODE": "report",
                "INPUT_RUN_ID": "",
                "INPUT_DB_PATH": str(tmp_path / "test.db"),
                "INPUT_MIN_RUNS": "3",
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
            }
        )
        assert result.returncode == 0

        summary = summary_file.read_text()
        assert len(summary.strip()) > 0


class TestActionOutputSafety:
    """Verify CLI output is safe for GitHub rendering."""

    def test_report_markdown_no_script_tags(self):
        result = run_cli("report", str(FIXTURES / "sample_junit.xml"), "--format", "markdown")
        assert "<script" not in result.stdout

    def test_report_markdown_has_table(self):
        result = run_cli("report", str(FIXTURES / "sample_junit.xml"), "--format", "markdown")
        table_lines = [line for line in result.stdout.split("\n") if "|" in line]
        assert len(table_lines) >= 2
