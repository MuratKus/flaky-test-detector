"""Markdown reporter — designed for GitHub PR comments and summaries."""

from flakydetector.models import FlakyTest, RunSummary


def report_flaky(flaky_tests: list[FlakyTest]) -> str:
    """Generate a markdown report of flaky tests."""
    if not flaky_tests:
        return "## Flaky Test Report\n\nNo flaky tests detected.\n"

    lines = [
        "## Flaky Test Report",
        "",
        f"**{len(flaky_tests)} flaky test(s) detected**",
        "",
    ]

    # Summary table
    quarantine = [t for t in flaky_tests if t.recommended_action == "quarantine"]
    investigate = [t for t in flaky_tests if t.recommended_action == "investigate"]
    monitor = [t for t in flaky_tests if t.recommended_action == "monitor"]

    if quarantine:
        lines.append(f"- :rotating_light: **Quarantine recommended:** {len(quarantine)}")
    if investigate:
        lines.append(f"- :mag: **Investigate:** {len(investigate)}")
    if monitor:
        lines.append(f"- :eyes: **Monitor:** {len(monitor)}")

    lines.extend(
        [
            "",
            "| Test | Flakiness | Runs | Pass/Fail | Action |",
            "|------|-----------|------|-----------|--------|",
        ]
    )

    for t in flaky_tests:
        pct = f"{t.flakiness_rate * 100:.0f}%"
        pf = f"{t.pass_count}/{t.fail_count}"
        icon = {"quarantine": ":rotating_light:", "investigate": ":mag:", "monitor": ":eyes:"}.get(
            t.recommended_action, ""
        )
        # Truncate long test names
        name = t.test_name if len(t.test_name) <= 60 else f"...{t.test_name[-57:]}"
        lines.append(
            f"| `{name}` | {pct} | {t.total_runs} | {pf} | {icon} {t.recommended_action} |"
        )

    lines.append("")
    return "\n".join(lines)


def report_run(summary: RunSummary) -> str:
    """Generate markdown summary of a single parsed run."""
    failures = [r for r in summary.results if r.outcome.value in ("failed", "error")]
    unique_fps = len({r.fingerprint for r in failures if r.fingerprint})

    lines = [
        "## Test Run Summary",
        "",
        f"**Run:** `{summary.run_id}` | **Source:** {summary.source}",
        "",
        "| Total | Passed | Failed | Errors | Skipped |",
        "|-------|--------|--------|--------|---------|",
        f"| {summary.total} | {summary.passed} | {summary.failed} | {summary.errored} | {summary.skipped} |",
        "",
    ]

    if failures:
        lines.append(f"### Failures ({len(failures)} total, {unique_fps} unique root cause(s))")
        lines.append("")

        # Group by fingerprint
        by_fp: dict[str, list] = {}
        for f in failures:
            fp = f.fingerprint or "no-fingerprint"
            by_fp.setdefault(fp, []).append(f)

        for fp, tests in by_fp.items():
            label = f"`{fp}`" if fp != "no-fingerprint" else "_(no stacktrace)_"
            lines.append(f"**Root cause {label}** — {len(tests)} test(s):")
            for t in tests:
                msg = t.error_message[:80] if t.error_message else "no message"
                lines.append(f"- `{t.fqn}`: {msg}")
            lines.append("")

    return "\n".join(lines)
