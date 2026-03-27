"""HTML reporter — self-contained HTML reports with inline SVG charts."""

import html
import math

from flakydetector.models import FlakyTest, RunSummary, TestOutcome


def _escape(text: str) -> str:
    """HTML-escape user-supplied text."""
    return html.escape(str(text), quote=True)


def _html_shell(title: str, body: str) -> str:
    """Wrap body content in a full HTML5 document with inline styles."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 0; padding: 2rem; background: #f8f9fa; color: #212529; }}
  h1 {{ margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #dee2e6; padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ background: #e9ecef; }}
  .badge {{ display: inline-block; padding: 0.2em 0.6em; border-radius: 4px;
            font-size: 0.85em; font-weight: 600; color: #fff; }}
  .badge-quarantine {{ background: #dc3545; }}
  .badge-investigate {{ background: #fd7e14; }}
  .badge-monitor {{ background: #0d6efd; }}
  .chart-container {{ display: inline-block; margin: 1rem 0; }}
  .summary-cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }}
  .card {{ background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
           padding: 1rem 1.5rem; min-width: 100px; text-align: center; }}
  .card-value {{ font-size: 1.8rem; font-weight: 700; }}
  .card-label {{ font-size: 0.85rem; color: #6c757d; }}
  .fp-group {{ background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
               padding: 1rem; margin: 0.75rem 0; }}
  .fp-header {{ font-weight: 600; margin-bottom: 0.5rem; }}
  .empty {{ color: #6c757d; font-style: italic; padding: 2rem 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def _flakiness_bar_chart(tests: list[FlakyTest]) -> str:
    """Generate an inline SVG horizontal bar chart of flakiness rates."""
    bar_height = 28
    gap = 6
    label_width = 220
    chart_width = 500
    total_width = label_width + chart_width + 60
    total_height = (bar_height + gap) * len(tests) + gap

    bars = []
    for i, t in enumerate(tests):
        y = gap + i * (bar_height + gap)
        pct = t.flakiness_rate * 100
        bar_w = max(1, t.flakiness_rate * chart_width)

        color = "#dc3545" if pct >= 50 else "#fd7e14" if pct >= 30 else "#0d6efd"

        name = _escape(t.test_name)
        if len(t.test_name) > 35:
            name = _escape("..." + t.test_name[-32:])

        bars.append(
            f'  <text x="{label_width - 8}" y="{y + bar_height * 0.7}" '
            f'text-anchor="end" font-size="12">{name}</text>'
        )
        bars.append(
            f'  <rect x="{label_width}" y="{y}" width="{bar_w:.1f}" '
            f'height="{bar_height}" rx="3" fill="{color}" />'
        )
        bars.append(
            f'  <text x="{label_width + bar_w + 6}" y="{y + bar_height * 0.7}" '
            f'font-size="12" fill="#495057">{pct:.0f}%</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" '
        f'height="{total_height}" role="img" aria-label="Flakiness chart">\n'
        + "\n".join(bars)
        + "\n</svg>"
    )


def _donut_chart(passed: int, failed: int, errored: int, skipped: int) -> str:
    """Generate an inline SVG donut chart for run outcome distribution."""
    total = passed + failed + errored + skipped
    if total == 0:
        return ""

    size = 160
    cx = cy = size / 2
    radius = 60
    stroke_width = 20

    segments = [
        (passed, "#28a745"),
        (failed, "#dc3545"),
        (errored, "#fd7e14"),
        (skipped, "#6c757d"),
    ]

    circumference = 2 * math.pi * radius
    paths = []
    offset = 0

    for count, color in segments:
        if count == 0:
            continue
        dash = (count / total) * circumference
        gap = circumference - dash
        paths.append(
            f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="{dash:.2f} {gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" />'
        )
        offset += dash

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" role="img" aria-label="Test outcome chart">\n'
        + "\n".join(paths)
        + f'\n  <text x="{cx}" y="{cy}" text-anchor="middle" '
        f'dominant-baseline="central" font-size="22" font-weight="700">'
        f"{total}</text>\n</svg>"
    )


def report_flaky(flaky_tests: list[FlakyTest]) -> str:
    """Generate a self-contained HTML report of flaky tests."""
    if not flaky_tests:
        body = "<h1>Flaky Test Report</h1>\n<p class=\"empty\">No flaky tests detected</p>"
        return _html_shell("Flaky Test Report", body)

    parts = ["<h1>Flaky Test Report</h1>"]
    parts.append(f"<p><strong>{len(flaky_tests)} flaky test(s) detected</strong></p>")

    # SVG chart
    parts.append('<div class="chart-container">')
    parts.append(_flakiness_bar_chart(flaky_tests))
    parts.append("</div>")

    # Table
    parts.append("<table>")
    parts.append(
        "<thead><tr>"
        "<th>Test</th><th>Flakiness</th><th>Runs</th>"
        "<th>Pass/Fail</th><th>Action</th>"
        "</tr></thead>"
    )
    parts.append("<tbody>")
    for t in flaky_tests:
        pct = t.flakiness_rate * 100
        badge_cls = {
            "quarantine": "badge-quarantine",
            "investigate": "badge-investigate",
            "monitor": "badge-monitor",
        }.get(t.recommended_action, "")
        parts.append(
            f"<tr>"
            f"<td>{_escape(t.test_name)}</td>"
            f"<td>{pct:.0f}%</td>"
            f"<td>{t.total_runs}</td>"
            f"<td>{t.pass_count}/{t.fail_count}</td>"
            f'<td><span class="badge {badge_cls}">{_escape(t.recommended_action)}</span></td>'
            f"</tr>"
        )
    parts.append("</tbody></table>")

    return _html_shell("Flaky Test Report", "\n".join(parts))


def report_run(summary: RunSummary) -> str:
    """Generate a self-contained HTML report of a single test run."""
    parts = ["<h1>Test Run Summary</h1>"]
    parts.append(f"<p><strong>Run:</strong> {_escape(summary.run_id)} "
                 f"| <strong>Source:</strong> {_escape(summary.source)}</p>")

    # Summary cards
    parts.append('<div class="summary-cards">')
    cards = [
        ("Total", summary.total, "#212529"),
        ("Passed", summary.passed, "#28a745"),
        ("Failed", summary.failed, "#dc3545"),
        ("Errors", summary.errored, "#fd7e14"),
        ("Skipped", summary.skipped, "#6c757d"),
    ]
    for label, value, color in cards:
        parts.append(
            f'<div class="card">'
            f'<div class="card-value" style="color:{color}">{value}</div>'
            f'<div class="card-label">{label}</div>'
            f"</div>"
        )
    parts.append("</div>")

    # Donut chart
    parts.append('<div class="chart-container">')
    parts.append(_donut_chart(summary.passed, summary.failed,
                              summary.errored, summary.skipped))
    parts.append("</div>")

    # Failures grouped by fingerprint
    failures = [r for r in summary.results
                if r.outcome in (TestOutcome.FAILED, TestOutcome.ERROR)]

    if failures:
        by_fp: dict[str, list] = {}
        for f in failures:
            fp = f.fingerprint or "no-fingerprint"
            by_fp.setdefault(fp, []).append(f)

        unique_fps = len({f.fingerprint for f in failures if f.fingerprint})
        parts.append(
            f"<h2>Failures ({len(failures)} total, "
            f"{unique_fps} unique root cause(s))</h2>"
        )

        for fp, tests in by_fp.items():
            fp_display = _escape(fp) if fp != "no-fingerprint" else "<em>no stacktrace</em>"
            parts.append('<div class="fp-group">')
            parts.append(
                f'<div class="fp-header">Root cause: '
                f'<code>{fp_display}</code> &mdash; {len(tests)} test(s)</div>'
            )
            parts.append("<ul>")
            for t in tests:
                msg = _escape(t.error_message[:80]) if t.error_message else "no message"
                parts.append(f"<li><code>{_escape(t.fqn)}</code>: {msg}</li>")
            parts.append("</ul>")
            parts.append("</div>")

    return _html_shell("Test Run Summary", "\n".join(parts))
