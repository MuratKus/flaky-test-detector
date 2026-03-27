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
@click.option("--format", "fmt", type=click.Choice(["json", "markdown", "html", "text"]), default="text")
@click.option("--min-runs", default=3, help="Minimum runs before flagging as flaky.")
@click.pass_context
def analyze(ctx, fmt, min_runs):
    """Analyze stored results and report flaky tests."""
    from flakydetector.analyzer import analyze as run_analysis
    from flakydetector.reporters import html_report, json_report, markdown

    store = Store(ctx.obj["db_path"])
    flaky_tests = run_analysis(store, min_runs=min_runs)

    if fmt == "json":
        click.echo(json_report.report_flaky(flaky_tests))
    elif fmt == "markdown":
        click.echo(markdown.report_flaky(flaky_tests))
    elif fmt == "html":
        click.echo(html_report.report_flaky(flaky_tests))
    else:
        if not flaky_tests:
            click.echo("No flaky tests detected.")
        else:
            click.echo(f"\n{len(flaky_tests)} flaky test(s) detected:\n")
            for t in flaky_tests:
                icon = {"quarantine": "🚨", "investigate": "🔍", "monitor": "👀"}.get(
                    t.recommended_action, ""
                )
                click.echo(
                    f"  {icon} {t.test_name}\n"
                    f"     flakiness={t.flakiness_rate:.0%}  "
                    f"runs={t.total_runs}  pass/fail={t.pass_count}/{t.fail_count}  "
                    f"→ {t.recommended_action}"
                )
                if t.failure_fingerprints:
                    click.echo(f"     fingerprints: {', '.join(t.failure_fingerprints[:3])}")
                click.echo()

    store.close()


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--run-id", default=None)
@click.option("--format", "fmt", type=click.Choice(["json", "markdown", "html", "text"]), default="text")
def report(path, run_id, fmt):
    """One-shot: parse and report without storing (stateless mode)."""
    from flakydetector.reporters import html_report, json_report, markdown

    path = Path(path)
    run_id = run_id or str(uuid.uuid4())[:8]
    files = _collect_files(path)

    for f in files:
        parser = _auto_detect_parser(f)
        if not parser:
            continue

        summary = parser.parse(f, run_id)
        fingerprint_results(summary.results)

        if fmt == "json":
            click.echo(json_report.report_run(summary))
        elif fmt == "markdown":
            click.echo(markdown.report_run(summary))
        elif fmt == "html":
            click.echo(html_report.report_run(summary))
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


if __name__ == "__main__":
    main()
