"""CLI for flaky-test-detector.

Usage:
    flaky-detect ingest <path> --run-id <id>     # parse + store results
    flaky-detect analyze                          # detect flaky tests
    flaky-detect report <path> --run-id <id>      # one-shot: parse and report (no store)
    flaky-detect history <test_name>              # show history for a test
    flaky-detect fingerprints                     # show common failure root causes
"""

import uuid
from pathlib import Path

import click

from flakydetector import __version__
from flakydetector.fingerprint import fingerprint_results
from flakydetector.parsers.allure_json import AllureJSONParser
from flakydetector.parsers.junit_xml import JUnitXMLParser
from flakydetector.parsers.plain_log import PlainLogParser
from flakydetector.store import Store

PARSERS = [JUnitXMLParser(), AllureJSONParser(), PlainLogParser()]


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def _auto_detect_parser(path: Path):
    """Try each parser and return the first one that can handle the file."""
    for parser in PARSERS:
        if parser.can_parse(path):
            return parser
    return None


def _collect_files(path: Path) -> list[Path]:
    """If path is a directory, collect all parseable files recursively."""
    if path.is_file():
        return [path]
    files = []
    for f in sorted(path.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            files.append(f)
    return files


@click.group()
@click.version_option(version=__version__)
@click.option("--db", default=".flaky-detector.db", help="Path to SQLite database.")
@click.pass_context
def main(ctx, db):
    """Flaky Test Detector — parse CI artifacts, fingerprint failures, detect flaky tests."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(db)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--run-id", default=None, help="Unique run identifier (auto-generated if omitted).")
@click.option("--format", "fmt", type=click.Choice(["json", "markdown", "text"]), default="text")
@click.pass_context
def ingest(ctx, path, run_id, fmt):
    """Parse test results and store them for flakiness tracking."""
    path = Path(path)
    run_id = run_id or str(uuid.uuid4())[:8]
    store = Store(ctx.obj["db_path"])

    files = _collect_files(path)
    total_results = 0

    for f in files:
        parser = _auto_detect_parser(f)
        if not parser:
            continue

        summary = parser.parse(f, run_id)
        fingerprint_results(summary.results)
        count = store.ingest(summary)
        total_results += count

        if fmt == "text":
            click.echo(
                f"  [{summary.source}] {f.name}: "
                f"{summary.passed}✓ {summary.failed}✗ {summary.errored}⚠ {summary.skipped}⊘"
            )

    if fmt == "text":
        click.echo(
            f"\nIngested {total_results} results from {len(files)} file(s) into run '{run_id}'."
        )
        click.echo(f"Total runs in DB: {store.get_run_count()}")
    elif fmt == "json":
        import json

        click.echo(json.dumps({"run_id": run_id, "results_ingested": total_results}))

    store.close()


@main.command()
@click.option(
    "--format", "fmt", type=click.Choice(["json", "markdown", "html", "text"]), default="text"
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write output to file instead of stdout.",
)
@click.option("--min-runs", default=3, help="Minimum runs before flagging as flaky.")
@click.option(
    "--threshold", default=0.2, type=float, help="Minimum flakiness rate to flag (0.0-1.0)."
)
@click.option(
    "--quarantine-at",
    default=0.5,
    type=float,
    help="Flakiness rate at or above which to recommend quarantine.",
)
@click.option(
    "--investigate-at",
    default=0.3,
    type=float,
    help="Flakiness rate at or above which to recommend investigation.",
)
@click.option("--ci-url", default=None, help="Link to CI run for 'View in CI' in HTML reports.")
@click.pass_context
def analyze(ctx, fmt, output_path, min_runs, threshold, quarantine_at, investigate_at, ci_url):
    """Analyze stored results and report flaky tests."""
    from flakydetector.analyzer import Thresholds
    from flakydetector.analyzer import analyze as run_analysis
    from flakydetector.reporters import html_report, json_report, markdown

    thresholds = Thresholds(
        min_flakiness=threshold,
        quarantine=quarantine_at,
        investigate=investigate_at,
    )
    store = Store(ctx.obj["db_path"])
    flaky_tests = run_analysis(store, min_runs=min_runs, thresholds=thresholds)

    if fmt == "json":
        output = json_report.report_flaky(flaky_tests)
    elif fmt == "markdown":
        output = markdown.report_flaky(flaky_tests)
    elif fmt == "html":
        output = html_report.report_flaky(flaky_tests, ci_url=ci_url)
    else:
        output = None

    if output is not None:
        if output_path:
            Path(output_path).write_text(output)
            click.echo(f"Report written to {output_path}")
        else:
            click.echo(output)
    else:
        if not flaky_tests:
            click.echo("No flaky tests detected.")
        else:
            total_wasted = sum(t.wasted_time_sec for t in flaky_tests)
            click.echo(f"\n{len(flaky_tests)} flaky test(s) detected:\n")
            for t in flaky_tests:
                icon = {"quarantine": "🚨", "investigate": "🔍", "monitor": "👀"}.get(
                    t.recommended_action, ""
                )
                trend_arrows = {
                    "improving": "📈",
                    "worsening": "📉",
                    "stable": "➡️",
                }
                trend_str = trend_arrows.get(t.trend_direction, "")
                wasted = _format_duration(t.wasted_time_sec)
                click.echo(
                    f"  {icon} {t.test_name}\n"
                    f"     flakiness={t.flakiness_rate:.0%}  "
                    f"runs={t.total_runs}  pass/fail={t.pass_count}/{t.fail_count}  "
                    f"→ {t.recommended_action}"
                )
                if t.wasted_time_sec > 0:
                    click.echo(f"     wasted CI time: {wasted}")
                if t.trend_direction:
                    spark = "".join("✓" if pt.outcome == "passed" else "✗" for pt in t.trend[-10:])
                    click.echo(f"     trend: {trend_str} {t.trend_direction}  [{spark}]")
                if t.failure_fingerprints:
                    click.echo(f"     fingerprints: {', '.join(t.failure_fingerprints[:3])}")
                click.echo()

            if total_wasted > 0:
                click.echo(
                    f"  ⏱  Total CI time wasted by flaky tests: {_format_duration(total_wasted)}"
                )

    store.close()


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--run-id", default=None)
@click.option(
    "--format", "fmt", type=click.Choice(["json", "markdown", "html", "text"]), default="text"
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write output to file instead of stdout.",
)
@click.option("--ci-url", default=None, help="Link to CI run for 'View in CI' in HTML reports.")
def report(path, run_id, fmt, output_path, ci_url):
    """One-shot: parse and report without storing (stateless mode)."""
    from flakydetector.reporters import html_report, json_report, markdown

    path = Path(path)
    run_id = run_id or str(uuid.uuid4())[:8]
    files = _collect_files(path)
    output_parts = []

    for f in files:
        parser = _auto_detect_parser(f)
        if not parser:
            continue

        summary = parser.parse(f, run_id)
        fingerprint_results(summary.results)

        if fmt == "json":
            output_parts.append(json_report.report_run(summary))
        elif fmt == "markdown":
            output_parts.append(markdown.report_run(summary))
        elif fmt == "html":
            output_parts.append(html_report.report_run(summary, ci_url=ci_url))
        else:
            click.echo(f"\n=== {f.name} ({summary.source}) ===")
            click.echo(
                f"Total: {summary.total} | ✓{summary.passed} ✗{summary.failed} ⚠{summary.errored} ⊘{summary.skipped}"
            )
            failures = [r for r in summary.results if r.outcome.value in ("failed", "error")]
            if failures:
                fps = {}
                for r in failures:
                    fp = r.fingerprint or "no-fp"
                    fps.setdefault(fp, []).append(r)
                click.echo(f"Failures: {len(failures)} ({len(fps)} unique root cause(s))")
                for fp, tests in fps.items():
                    click.echo(f"\n  [{fp}] {len(tests)} test(s):")
                    for t in tests:
                        msg = (t.error_message or "")[:80]
                        click.echo(f"    - {t.fqn}: {msg}")

    if output_parts:
        combined = "\n".join(output_parts)
        if output_path:
            Path(output_path).write_text(combined)
            click.echo(f"Report written to {output_path}")
        else:
            click.echo(combined)


@main.command()
@click.argument("test_name")
@click.pass_context
def history(ctx, test_name):
    """Show outcome history for a specific test."""
    store = Store(ctx.obj["db_path"])
    records = store.get_test_history(test_name)

    if not records:
        click.echo(f"No history found for '{test_name}'.")
        store.close()
        return

    click.echo(f"\nHistory for: {test_name} ({len(records)} runs)\n")
    for r in records:
        icon = "✓" if r["outcome"] == "passed" else "✗"
        fp = f" [{r['fingerprint'][:8]}]" if r["fingerprint"] else ""
        click.echo(f"  {icon} {r['outcome']:8s} {r['run_id']:8s} {r['ingested_at']}{fp}")

    store.close()


@main.command()
@click.pass_context
def fingerprints(ctx):
    """Show common failure root causes grouped by stacktrace fingerprint."""
    store = Store(ctx.obj["db_path"])
    groups = store.get_failure_fingerprint_counts()

    if not groups:
        click.echo("No failure fingerprints in database.")
        store.close()
        return

    click.echo(f"\nTop failure root causes ({len(groups)} distinct):\n")
    for g in groups:
        tests = g["tests"].split(",") if g["tests"] else []
        click.echo(
            f"  [{g['fingerprint'][:12]}] {g['count']} occurrence(s) across {len(tests)} test(s)"
        )
        click.echo(f"    sample: {(g['sample_error'] or '')[:100]}")
        for t in tests[:3]:
            click.echo(f"    - {t}")
        if len(tests) > 3:
            click.echo(f"    ... and {len(tests) - 3} more")
        click.echo()

    store.close()


@main.command()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["pytest", "junit", "json"]),
    default="json",
    help="Output format for the quarantine list.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write output to file instead of stdout.",
)
@click.option("--min-runs", default=3, help="Minimum runs before flagging as flaky.")
@click.option(
    "--include",
    "include_actions",
    default="quarantine",
    help="Comma-separated actions to include (quarantine,investigate,monitor).",
)
@click.pass_context
def quarantine(ctx, fmt, output_path, min_runs, include_actions):
    """Export quarantined tests in a format test runners can consume."""
    from flakydetector.analyzer import analyze as run_analysis
    from flakydetector.quarantine import export_json, export_junit, export_pytest

    store = Store(ctx.obj["db_path"])
    flaky_tests = run_analysis(store, min_runs=min_runs)

    actions = [a.strip() for a in include_actions.split(",")]

    if fmt == "pytest":
        output = export_pytest(flaky_tests, actions=actions)
    elif fmt == "junit":
        output = export_junit(flaky_tests, actions=actions)
    else:
        output = export_json(flaky_tests, actions=actions)

    if output_path:
        Path(output_path).write_text(output)
        click.echo(f"Quarantine list written to {output_path}")
    else:
        click.echo(output)

    store.close()


@main.command()
@click.argument("test_name")
@click.option("--fingerprint", default=None, help="Restrict to one failure pattern.")
@click.option("--repo-path", default=".", type=click.Path(), help="Path to the git repository.")
@click.option(
    "--format", "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format.",
)
@click.option("--max-commits", default=20, help="Recent commits to consider.")
@click.option("--model", default="claude-sonnet-4-6", help="Claude model ID.")
@click.option("--no-cache", is_flag=True, default=False, help="Force fresh investigation.")
@click.pass_context
def investigate(ctx, test_name, fingerprint, repo_path, fmt, max_commits, model, no_cache):
    """Investigate why a flaky test fails using AI analysis."""
    import json as _json
    from flakydetector.investigator import investigate as run_investigation

    store = Store(ctx.obj["db_path"])
    try:
        result = run_investigation(
            test_name=test_name,
            store=store,
            repo_path=Path(repo_path),
            fingerprint=fingerprint,
            max_commits=max_commits,
            model=model,
            use_cache=not no_cache,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        store.close()
        raise SystemExit(1)

    if fmt == "json":
        click.echo(_json.dumps(result.__dict__, indent=2))
    else:
        cached_note = " (cached)" if result.cached else ""
        click.echo(f"Test: {result.test_name}")
        click.echo(f"\nCATEGORY ({result.confidence} confidence){cached_note}")
        click.echo(f"  {result.category}")
        click.echo("\nEVIDENCE")
        for e in result.evidence:
            click.echo(f"  - {e['fact']} [source: {e['source']}]")
        if result.not_supported:
            click.echo("\nNOT SUPPORTED BY EVIDENCE")
            for item in result.not_supported:
                click.echo(f"  - {item}")
        click.echo("\nSUGGESTED FIX DIRECTION")
        click.echo(f"  {result.suggested_fix}")

    store.close()


if __name__ == "__main__":
    main()
