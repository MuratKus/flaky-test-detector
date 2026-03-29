"""GitHub Action entrypoint for flaky-test-detector.

Reads inputs from environment variables (INPUT_*), runs the CLI,
and writes outputs to GITHUB_OUTPUT / GITHUB_STEP_SUMMARY.
"""

import json
import os
import subprocess
import sys


def get_input(name: str, default: str = "") -> str:
    """Read a GitHub Action input from environment."""
    return os.environ.get(f"INPUT_{name.upper().replace('-', '_')}", default)


def write_output(name: str, value: str) -> None:
    """Write a value to GITHUB_OUTPUT."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        return
    with open(output_file, "a") as f:
        if "\n" in value:
            f.write(f"{name}<<EOF\n{value}\nEOF\n")
        else:
            f.write(f"{name}={value}\n")


def write_summary(content: str) -> None:
    """Append content to GITHUB_STEP_SUMMARY."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_file:
        return
    with open(summary_file, "a") as f:
        f.write(content + "\n")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the flaky-detect CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "flakydetector.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _get_ci_url() -> str | None:
    """Build the CI run URL from GitHub environment, or from action input."""
    ci_url = get_input("ci_url") or get_input("ci-url")
    if ci_url:
        return ci_url
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def _write_html_artifact(args_base: list[str]) -> None:
    """Generate an HTML report and write it to a file for artifact upload."""
    html_args = [*args_base, "--format", "html"]
    ci_url = _get_ci_url()
    if ci_url:
        html_args.extend(["--ci-url", ci_url])
    html_result = run_cli(*html_args)
    if html_result.returncode == 0 and html_result.stdout.strip():
        html_path = os.environ.get("INPUT_HTML_REPORT_PATH", "flaky-report.html")
        with open(html_path, "w") as f:
            f.write(html_result.stdout)
        write_output("html_report_path", html_path)


def _report_mode(path: str, run_id: str) -> int:
    """One-shot: parse artifacts and produce a markdown report."""
    args = ["report", path, "--format", "markdown"]
    base_args = ["report", path]
    if run_id:
        args.extend(["--run-id", run_id])
        base_args.extend(["--run-id", run_id])

    result = run_cli(*args)
    if result.returncode != 0:
        print(f"::error::flaky-detect report failed: {result.stderr}")
        return result.returncode

    report = result.stdout.strip()
    write_output("report", report)
    write_summary(report)

    # Get JSON for structured outputs
    json_args = [*base_args, "--format", "json"]
    json_result = run_cli(*json_args)
    if json_result.returncode == 0:
        try:
            data = json.loads(json_result.stdout)
            write_output("total_tests", str(data.get("total", 0)))
        except json.JSONDecodeError:
            pass

    # Generate HTML artifact
    _write_html_artifact(base_args)

    return 0


def _analyze_mode(path: str, run_id: str, db_path: str, min_runs: str) -> int:
    """Multi-run: ingest artifacts, then analyze for flakiness."""
    # Ingest
    ingest_args = ["--db", db_path, "ingest", path]
    if run_id:
        ingest_args.extend(["--run-id", run_id])

    ingest_result = run_cli(*ingest_args)
    if ingest_result.returncode != 0:
        print(f"::error::flaky-detect ingest failed: {ingest_result.stderr}")
        return ingest_result.returncode

    # Analyze — markdown
    result = run_cli("--db", db_path, "analyze", "--format", "markdown", "--min-runs", min_runs)
    if result.returncode != 0:
        print(f"::error::flaky-detect analyze failed: {result.stderr}")
        return result.returncode

    report = result.stdout.strip()
    write_output("report", report)
    write_summary(report)

    # Analyze — JSON for structured outputs
    json_result = run_cli("--db", db_path, "analyze", "--format", "json", "--min-runs", min_runs)
    if json_result.returncode == 0:
        try:
            data = json.loads(json_result.stdout)
            write_output("flaky_count", str(data.get("total_flaky", 0)))
        except json.JSONDecodeError:
            pass

    # Generate HTML artifact
    _write_html_artifact(["--db", db_path, "analyze", "--min-runs", min_runs])

    return 0


def main() -> int:
    path = get_input("path")
    mode = get_input("mode", "report")
    run_id = get_input("run_id") or get_input("run-id")
    db_path = get_input("db_path") or get_input("db-path", ".flaky-detector.db")
    min_runs = get_input("min_runs") or get_input("min-runs", "3")

    if not path:
        print("::error::Input 'path' is required")
        return 1

    if mode == "report":
        return _report_mode(path, run_id)
    elif mode == "analyze":
        return _analyze_mode(path, run_id, db_path, min_runs)
    else:
        print(f"::error::Unknown mode '{mode}'. Use 'report' or 'analyze'.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
