"""HTML reporter — self-contained HTML reports with dark theme and inline SVG charts."""

import html
from datetime import UTC, datetime

from flakydetector import __version__
from flakydetector.models import FlakyTest, RunSummary, TestOutcome

# -- Design tokens (from Tailwind config) --
_C = {
    "bg": "#0b1326",
    "surface": "#0b1326",
    "surface_container": "#171f33",
    "surface_container_low": "#131b2e",
    "surface_container_high": "#222a3d",
    "surface_container_highest": "#2d3449",
    "surface_container_lowest": "#060e20",
    "on_surface": "#dae2fd",
    "on_surface_variant": "#c2c6d6",
    "outline": "#8c909f",
    "outline_variant": "#424754",
    "primary": "#adc6ff",
    "primary_fixed_dim": "#adc6ff",
    "primary_container": "#4d8eff",
    "secondary": "#4edea3",
    "tertiary": "#fbbf24",
    "tertiary_container": "#92400e",
    "error": "#ffb4ab",
    "error_container": "#93000a",
    "on_error_container": "#ffdad6",
    "on_tertiary_container": "#fef3c7",
}


def _escape(text: str) -> str:
    return html.escape(str(text), quote=True)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _html_shell(title: str, body: str) -> str:
    """Wrap body in full HTML5 doc with design-matched inline styles."""
    c = _C
    return f"""<!DOCTYPE html>
<html class="dark" lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&amp;family=Inter:wght@300;400;500;600;700&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: {c["bg"]}; color: {c["on_surface"]};
    min-height: 100vh; display: flex; flex-direction: column; align-items: center;
  }}
  main {{ width: 100%; max-width: 90rem; padding: 4rem 2.5rem 3rem; }}
  code, .mono {{ font-family: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', Consolas, monospace; }}
  .font-headline {{ font-family: 'Space Grotesk', 'Inter', sans-serif; }}

  /* Brand & header */
  .brand {{ color: {c["primary"]}; font-weight: 700; font-size: 1.25rem;
            font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.03em; margin-bottom: 1rem; }}
  .subtitle {{ color: {c["primary"]}; font-family: 'JetBrains Mono', monospace;
               font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.15em;
               font-weight: 500; margin-bottom: 0.5rem; }}
  h1 {{ font-family: 'Space Grotesk', sans-serif; font-size: 2.5rem;
        font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }}
  h2 {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.125rem;
        font-weight: 700; color: {c["on_surface"]}; display: flex; align-items: center; gap: 0.5rem; }}
  .timestamp {{ font-size: 0.875rem; color: {c["on_surface_variant"]}; opacity: 0.7;
                font-family: 'JetBrains Mono', monospace; margin-top: 0.25rem; }}
  .header-row {{ display: flex; flex-wrap: wrap; justify-content: space-between;
                 align-items: flex-end; gap: 1.5rem; margin-bottom: 2.5rem; }}

  /* Tags */
  .tag {{ display: inline-block; padding: 0.15em 0.5em; border-radius: 0.25rem;
          font-size: 0.625rem; font-weight: 700; font-family: 'JetBrains Mono', monospace;
          text-transform: uppercase; letter-spacing: -0.02em;
          border: 1px solid {c["outline_variant"]}33; margin-right: 0.5rem; }}
  .tag-primary {{ background: {c["surface_container_highest"]}; color: {c["primary_fixed_dim"]}; }}
  .tag-muted {{ background: {c["surface_container_lowest"]}; color: {c["on_surface_variant"]}; }}

  /* Summary cards */
  .summary-cards {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .card {{ background: {c["surface_container_low"]}; border-radius: 0.5rem;
           padding: 1.25rem; min-width: 110px; border-left: 4px solid transparent;
           flex: 1; }}
  .card-label {{ font-size: 0.625rem; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 0.15em; margin-bottom: 0.25rem; }}
  .card-value {{ font-size: 2.25rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif; }}
  .card-bar {{ height: 4px; width: 100%; background: {c["surface_container"]};
               border-radius: 9999px; overflow: hidden; margin-top: 1rem; }}
  .card-bar-fill {{ height: 100%; border-radius: 9999px; }}

  /* Section containers */
  .section {{ background: {c["surface_container_low"]}; border-radius: 0.75rem;
              padding: 1.5rem; margin-bottom: 3rem; position: relative; overflow: hidden; }}
  .section-alt {{ background: {c["surface_container"]}; border-radius: 0.75rem;
                  overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4); margin-bottom: 3rem; }}
  .section-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }}
  .section-title {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.125rem; font-weight: 600;
                    display: flex; align-items: center; gap: 0.5rem; }}
  .section-badge {{ font-size: 0.625rem; font-family: 'JetBrains Mono', monospace;
                    color: {c["outline"]}; padding: 0.25em 0.5em;
                    background: {c["surface_container"]}; border-radius: 0.25rem; }}

  /* Impact distribution bars */
  .bar-row {{ margin-bottom: 1.5rem; }}
  .bar-row:last-child {{ margin-bottom: 0; }}
  .bar-meta {{ display: flex; justify-content: space-between; align-items: baseline;
               font-size: 0.6875rem; font-family: 'JetBrains Mono', monospace;
               color: {c["outline"]}; margin-bottom: 0.5rem; }}
  .bar-track {{ height: 8px; background: {c["surface_container_highest"]}; border-radius: 9999px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 9999px; }}

  /* Table */
  .table-header {{ padding: 1.5rem; border-bottom: 1px solid {c["outline_variant"]}1a;
                   background: {c["surface_container_high"]}4d;
                   display: flex; align-items: center; justify-content: space-between; }}
  .table-title {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.125rem; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.15em;
        color: {c["outline"]}; font-weight: 600; text-align: left;
        padding: 1rem 1.5rem; background: {c["surface_container_high"]}80; }}
  td {{ padding: 1rem 1.5rem; border-bottom: 1px solid {c["outline_variant"]}0d;
        font-size: 0.875rem; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: {c["surface_container_high"]}66; }}
  .test-name {{ font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;
                color: {c["on_surface"]}; }}
  .flakiness-pct {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.9rem; }}
  .runs-count {{ font-family: 'JetBrains Mono', monospace; font-size: 0.875rem; color: {c["outline"]}; }}
  .td-name {{ display: flex; align-items: center; gap: 0.75rem; }}

  /* Pass/fail mini bar */
  .pf-container {{ display: flex; align-items: center; gap: 0.5rem; }}
  .pf-bar {{ display: flex; height: 6px; width: 6rem; background: {c["surface_container_highest"]};
             border-radius: 9999px; overflow: hidden; }}
  .pf-pass {{ height: 100%; }}
  .pf-fail {{ height: 100%; }}
  .pf-text {{ font-size: 0.625rem; font-family: 'JetBrains Mono', monospace; color: {c["outline"]}; }}

  /* Action badges */
  .badge {{ display: inline-block; padding: 0.25em 0.5em; border-radius: 0.25rem;
            font-size: 0.625rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: -0.02em; }}
  .badge-quarantine {{ background: {c["error"]}1a; color: {c["error"]};
                       border: 1px solid {c["error"]}33; }}
  .badge-investigate {{ background: {c["tertiary"]}1a; color: {c["tertiary"]};
                        border: 1px solid {c["tertiary"]}33; }}
  .badge-monitor {{ background: {c["primary"]}1a; color: {c["primary"]};
                    border: 1px solid {c["primary"]}33; }}

  /* Status icons (unicode fallback for Material Symbols) */
  .icon {{ display: inline-flex; align-items: center; justify-content: center;
           width: 20px; height: 20px; font-size: 14px; flex-shrink: 0; }}
  .icon-quarantine {{ color: {c["error"]}; }}
  .icon-investigate {{ color: {c["tertiary"]}; }}
  .icon-monitor {{ color: {c["primary"]}; }}

  /* Donut chart */
  .chart-wrapper {{ display: flex; align-items: center; justify-content: center;
                    background: {c["surface_container_low"]}; border-radius: 0.5rem; padding: 1.5rem; }}
  .donut-label {{ position: absolute; inset: 0; display: flex; flex-direction: column;
                  align-items: center; justify-content: center; pointer-events: none; }}
  .donut-pct {{ font-size: 1.5rem; font-family: 'Space Grotesk', sans-serif;
                font-weight: 700; color: {c["on_surface"]}; line-height: 1; }}
  .donut-sub {{ font-size: 0.625rem; font-weight: 700; color: {c["on_surface_variant"]};
                text-transform: uppercase; letter-spacing: -0.02em; }}

  /* Summary grid (run report) */
  .summary-grid {{ display: grid; grid-template-columns: 1fr; gap: 1.5rem; margin-bottom: 3rem; }}
  @media (min-width: 1024px) {{
    .summary-grid {{ grid-template-columns: 9fr 3fr; }}
  }}
  .cards-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }}
  @media (min-width: 640px) {{
    .cards-grid {{ grid-template-columns: repeat(3, 1fr); }}
  }}
  @media (min-width: 1280px) {{
    .cards-grid {{ grid-template-columns: repeat(5, 1fr); }}
  }}

  /* Failure groups */
  .fp-group {{ background: {c["surface_container"]}; border-radius: 0.75rem;
               overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
               margin-bottom: 1.5rem; }}
  .fp-header {{ display: flex; justify-content: space-between; align-items: center;
                padding: 1rem 1.5rem; background: {c["surface_container_high"]};
                border-bottom: 1px solid {c["outline_variant"]}1a; }}
  .fp-header-left {{ display: flex; align-items: center; gap: 1rem; }}
  .fp-id {{ font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; font-weight: 700;
            color: {c["primary_fixed_dim"]}; background: {c["surface_container_highest"]};
            padding: 0.25em 0.5em; border-radius: 0.25rem; }}
  .fp-title {{ font-family: 'JetBrains Mono', monospace; font-size: 0.875rem;
               font-weight: 500; color: {c["on_surface"]}; }}
  .fp-count {{ font-size: 0.625rem; font-weight: 700; text-transform: uppercase;
               letter-spacing: 0.08em; padding: 0.3em 0.75em; border-radius: 9999px; }}
  .fp-count-fail {{ background: {c["error_container"]}; color: {c["on_error_container"]}; }}
  .fp-count-error {{ background: {c["tertiary_container"]}; color: {c["on_tertiary_container"]}; }}
  .fp-body {{ padding: 1.5rem; }}
  .fp-label {{ font-size: 0.625rem; font-weight: 700; color: {c["on_surface_variant"]};
               text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 0.75rem; }}
  .fp-tests {{ display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }}
  .fp-test {{ display: flex; align-items: center; gap: 0.75rem; font-size: 0.75rem;
              font-family: 'JetBrains Mono', monospace; color: {c["on_surface"]};
              background: {c["surface_container_lowest"]}; padding: 0.5rem;
              border-radius: 0.25rem; }}
  .fp-test-fail {{ border-left: 2px solid {c["error"]}; }}
  .fp-test-error {{ border-left: 2px solid {c["tertiary"]}; }}
  .fp-test-icon-fail {{ color: {c["error"]}; font-size: 1rem; }}
  .fp-test-icon-error {{ color: {c["tertiary"]}; font-size: 1rem; }}
  .fp-snippet {{ background: {c["surface_container_lowest"]}; padding: 1rem;
                 border-radius: 0.25rem; margin-top: 0.75rem; }}
  .fp-snippet-fail {{ border-left: 4px solid {c["error"]}4d; }}
  .fp-snippet-error {{ border-left: 4px solid {c["tertiary"]}4d; }}
  .fp-snippet-label {{ font-size: 0.625rem; font-weight: 700; text-transform: uppercase;
                       letter-spacing: 0.15em; margin-bottom: 0.5rem; }}
  .fp-snippet-label-fail {{ color: {c["error"]}; }}
  .fp-snippet-label-error {{ color: {c["tertiary"]}; }}
  .fp-snippet code {{ font-size: 0.875rem; font-family: 'JetBrains Mono', monospace;
                      line-height: 1.6; white-space: pre-wrap; word-break: break-all; }}
  .fp-snippet-fail code {{ color: {c["error"]}e6; }}
  .fp-snippet-error code {{ color: {c["tertiary"]}e6; }}

  /* Footer */
  .footer {{ width: 100%; max-width: 90rem; display: flex; flex-wrap: wrap;
             justify-content: space-between; align-items: center;
             padding: 1.5rem 1.5rem; margin-top: auto; gap: 1rem;
             font-family: 'JetBrains Mono', monospace; font-size: 0.625rem;
             text-transform: uppercase; letter-spacing: 0.15em; color: {c["outline"]}; }}
  .footer strong {{ color: {c["outline"]}; font-weight: 700; }}
  .footer a {{ color: {c["primary"]}; text-decoration: none; }}

  /* Muted text helper */
  .text-muted {{ color: {c["on_surface_variant"]}; }}
  .text-sm {{ font-size: 0.875rem; font-weight: 400; }}
</style>
</head>
<body>
{body}
<div class="footer">
  <div style="display:flex;align-items:center;gap:1.5rem">
    <strong>flaky-test-detector</strong>
    <span>v{__version__}</span>
  </div>
  <div style="display:flex;align-items:center;gap:0.5rem">
    <span>&copy; {datetime.now(UTC).year} flaky-test-detector</span>
    <span style="opacity:0.3;margin:0 0.25rem">|</span>
    <span>Generated: {_timestamp()}</span>
  </div>
</div>
</body>
</html>"""


# -- Icons (unicode fallbacks for Material Symbols) --
_ICON_DANGEROUS = "\u2716"  # ✖
_ICON_WARNING = "\u26a0"  # ⚠
_ICON_SEARCH = "\u2315"  # ⌕
_ICON_VISIBILITY = "\u25c9"  # ◉
_ICON_CLOSE = "\u2715"  # ✕
_ICON_ERROR = "\u25cf"  # ●
_ICON_BAR_CHART = "\u2581\u2583\u2585"


def _action_icon(action: str) -> str:
    icons = {
        "quarantine": (_ICON_DANGEROUS, "icon-quarantine"),
        "investigate": (_ICON_SEARCH, "icon-investigate"),
        "monitor": (_ICON_VISIBILITY, "icon-monitor"),
    }
    sym, cls = icons.get(action, ("?", ""))
    return f'<span class="icon {cls}">{sym}</span>'


def _passfail_bar(passes: int, fails: int, action: str = "error") -> str:
    total = passes + fails
    if total == 0:
        return ""
    pass_pct = (passes / total) * 100
    fail_color = {
        "quarantine": _C["error"],
        "investigate": _C["tertiary"],
        "monitor": _C["primary"],
    }.get(action, _C["error"])
    return (
        f'<div class="pf-container">'
        f'<div class="pf-bar">'
        f'<div class="pf-pass" style="width:{pass_pct:.0f}%;background:{_C["secondary"]}"></div>'
        f'<div class="pf-fail" style="width:{100 - pass_pct:.0f}%;background:{fail_color}"></div>'
        f"</div>"
        f'<span class="pf-text">{passes}P / {fails}F</span>'
        f"</div>"
    )


def _bar_color_for_action(action: str) -> str:
    return {
        "quarantine": _C["error"],
        "investigate": _C["tertiary"],
        "monitor": _C["primary"],
    }.get(action, _C["error"])


def _flakiness_bar_chart(tests: list[FlakyTest]) -> str:
    rows = []
    for t in tests:
        pct = t.flakiness_rate * 100
        color = _bar_color_for_action(t.recommended_action)
        rows.append(
            f'<div class="bar-row">'
            f'<div class="bar-meta">'
            f"<span>{_escape(t.test_name)}</span>"
            f'<span style="color:{color}">{pct:.0f}%</span>'
            f"</div>"
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width:{pct:.1f}%;background:{color}"></div>'
            f"</div>"
            f"</div>"
        )
    return "\n".join(rows)


def _donut_chart(passed: int, failed: int, errored: int, skipped: int) -> str:
    total = passed + failed + errored + skipped
    if total == 0:
        return ""

    c = _C
    success_pct = round((passed / total) * 100)

    # Using viewBox 36x36 approach from the design
    segments = [
        (passed, c["secondary"], "Passed"),
        (failed, c["error"], "Failed"),
        (errored, c["tertiary"], "Errors"),
        (skipped, c["outline"], "Skipped"),
    ]

    circles = []
    offset = 0
    for count, color, _label in segments:
        if count == 0:
            continue
        pct = (count / total) * 100
        circles.append(
            f'<circle cx="18" cy="18" r="16" fill="none" stroke="{color}" '
            f'stroke-width="3.5" stroke-dasharray="{pct:.1f}, 100" '
            f'stroke-dashoffset="{-offset:.1f}" />'
        )
        offset += pct

    return (
        f'<div class="chart-wrapper">'
        f'<div style="position:relative;width:160px;height:160px">'
        f'<svg viewBox="0 0 36 36" style="width:100%;height:100%;transform:rotate(-90deg)">'
        f'<circle cx="18" cy="18" r="16" fill="none" stroke="{c["surface_container"]}" stroke-width="3.5" />'
        + "\n".join(circles)
        + f"</svg>"
        f'<div class="donut-label">'
        f'<span class="donut-pct">{success_pct}%</span>'
        f'<span class="donut-sub">Success</span>'
        f"</div></div></div>"
    )


def report_flaky(flaky_tests: list[FlakyTest], *, ci_url: str | None = None) -> str:
    """Generate a self-contained HTML report of flaky tests."""
    if not flaky_tests:
        body = (
            "<main>"
            '<div class="brand">flaky-test-detector</div>'
            '<p class="subtitle">Stability Report</p>'
            "<h1>No Flaky Tests Detected</h1>"
            "</main>"
        )
        return _html_shell("Flaky Test Report", body)

    c = _C
    quarantine_count = sum(1 for t in flaky_tests if t.recommended_action == "quarantine")
    investigate_count = sum(1 for t in flaky_tests if t.recommended_action == "investigate")
    monitor_count = sum(1 for t in flaky_tests if t.recommended_action == "monitor")

    parts = ["<main>"]

    # Header
    parts.append('<div class="header-row">')
    parts.append("<div>")
    parts.append('<div class="brand">flaky-test-detector</div>')
    parts.append('<p class="subtitle">Stability Report</p>')
    parts.append(f"<h1>{len(flaky_tests)} Flaky Test(s) Detected</h1>")
    if ci_url:
        parts.append(
            f'<a href="{_escape(ci_url)}" target="_blank" rel="noopener" '
            f'style="display:inline-flex;align-items:center;gap:0.5rem;margin-top:0.5rem;'
            f"font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:{c['primary']};"
            f'text-decoration:none">'
            f"&#x2197; View in CI</a>"
        )
    parts.append("</div>")

    # Summary cards
    parts.append('<div style="display:flex;gap:1rem">')
    summary = [
        ("Critical", str(quarantine_count), c["error"]),
        ("Investigating", str(investigate_count), c["tertiary"]),
        ("Monitoring", str(monitor_count), c["primary"]),
    ]
    for label, value, color in summary:
        parts.append(
            f'<div class="card" style="border-left-color:{color};min-width:140px">'
            f'<div class="card-label" style="color:{c["on_surface_variant"]}">{label}</div>'
            f'<div class="card-value" style="color:{color}">{value}</div>'
            f"</div>"
        )
    parts.append("</div>")
    parts.append("</div>")  # header-row

    # Impact Distribution
    parts.append('<div class="section">')
    parts.append('<div class="section-header">')
    parts.append(f'<div class="section-title">{_ICON_BAR_CHART} Impact Distribution</div>')
    parts.append('<span class="section-badge">SORTED BY % FLAKINESS</span>')
    parts.append("</div>")
    parts.append(_flakiness_bar_chart(flaky_tests))
    parts.append("</div>")

    # Detailed Analysis table
    parts.append('<div class="section-alt">')
    parts.append('<div class="table-header">')
    parts.append('<div class="table-title">Detailed Analysis</div>')
    parts.append('<div style="display:flex;gap:0.75rem;align-items:center">')
    parts.append(
        f'<input id="search-input" type="text" placeholder="Filter tests\u2026"'
        f' style="background:{c["surface_container"]};color:{c["on_surface"]};'
        f"border:1px solid {c['outline_variant']};border-radius:0.375rem;"
        f"padding:0.375rem 0.75rem;font-size:0.75rem;font-family:'JetBrains Mono',monospace;"
        f'outline:none;width:14rem" />'
    )
    parts.append(
        f'<button id="export-json"'
        f' style="background:{c["surface_container"]};color:{c["primary"]};'
        f"border:1px solid {c['outline_variant']};border-radius:0.375rem;"
        f"padding:0.375rem 0.75rem;font-size:0.625rem;font-weight:700;"
        f"font-family:'JetBrains Mono',monospace;text-transform:uppercase;"
        f'letter-spacing:0.08em;cursor:pointer">'
        f"&#x21E9; Export JSON</button>"
    )
    parts.append("</div>")
    parts.append("</div>")
    parts.append('<div style="overflow-x:auto">')
    parts.append("<table>")
    parts.append(
        "<thead><tr>"
        "<th>Test Name</th><th>Flakiness %</th><th>Runs</th>"
        "<th>Pass / Fail</th><th>Recommended Action</th>"
        "</tr></thead>"
    )
    parts.append("<tbody>")
    for t in flaky_tests:
        pct = t.flakiness_rate * 100
        pct_color = _bar_color_for_action(t.recommended_action)
        badge_cls = {
            "quarantine": "badge-quarantine",
            "investigate": "badge-investigate",
            "monitor": "badge-monitor",
        }.get(t.recommended_action, "")

        parts.append(
            f"<tr>"
            f'<td><div class="td-name">{_action_icon(t.recommended_action)}'
            f'<span class="test-name">{_escape(t.test_name)}</span></div></td>'
            f'<td class="flakiness-pct" style="color:{pct_color}">{pct:.0f}%</td>'
            f'<td class="runs-count">{t.total_runs}</td>'
            f"<td>{_passfail_bar(t.pass_count, t.fail_count, t.recommended_action)}</td>"
            f'<td><span class="badge {badge_cls}">{_escape(t.recommended_action)}</span></td>'
            f"</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("</div>")  # overflow wrapper
    parts.append("</div>")  # section-alt

    # Inline JS: search filter + export JSON
    parts.append("<script>")
    parts.append("(function(){")
    # Search filter
    parts.append(
        'var input=document.getElementById("search-input");'
        'var rows=document.querySelectorAll("tbody tr");'
        'input.addEventListener("input",function(){'
        "var q=this.value.toLowerCase();"
        "rows.forEach(function(r){"
        'var name=r.querySelector(".test-name");'
        'r.style.display=name&&name.textContent.toLowerCase().indexOf(q)===-1?"none":"";'
        "});"
        "});"
    )
    # Export JSON
    parts.append(
        'document.getElementById("export-json").addEventListener("click",function(){'
        "var data=[];"
        "rows.forEach(function(r){"
        'var name=r.querySelector(".test-name");'
        'var pct=r.querySelector(".flakiness-pct");'
        'var runs=r.querySelector(".runs-count");'
        'var badge=r.querySelector(".badge");'
        "if(name)data.push({"
        "test_name:name.textContent,"
        'flakiness:pct?pct.textContent:"",'
        'runs:runs?runs.textContent:"",'
        'action:badge?badge.textContent:""'
        "});"
        "});"
        "var blob=new Blob([JSON.stringify(data,null,2)],"
        '{type:"application/json"});'
        'var a=document.createElement("a");'
        "a.href=URL.createObjectURL(blob);"
        'a.download="flaky-tests.json";'
        "a.click();"
        "});"
    )
    parts.append("})();")
    parts.append("</script>")

    parts.append("</main>")
    return _html_shell("Flaky Test Report", "\n".join(parts))


def report_run(summary: RunSummary, *, ci_url: str | None = None) -> str:
    """Generate a self-contained HTML report of a single test run."""
    c = _C
    parts = ["<main>"]

    # Header
    parts.append('<div class="header-row">')
    parts.append("<div>")
    parts.append(
        f'<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">'
        f'<span class="tag tag-primary">{_escape(summary.run_id)}</span>'
        f'<span class="tag tag-muted">{_escape(summary.source)}</span>'
        f"</div>"
    )
    parts.append("<h1>Test Run Summary</h1>")
    parts.append(f'<p class="timestamp">Executed at {_timestamp()}</p>')
    if ci_url:
        parts.append(
            f'<a href="{_escape(ci_url)}" target="_blank" rel="noopener" '
            f'style="display:inline-flex;align-items:center;gap:0.5rem;margin-top:0.5rem;'
            f"font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:{c['primary']};"
            f'text-decoration:none">'
            f"&#x2197; View in CI</a>"
        )
    parts.append("</div>")
    parts.append("</div>")

    # Summary grid: cards + donut
    total = summary.total or 1
    parts.append('<div class="summary-grid">')

    # Cards
    parts.append('<div class="cards-grid">')
    cards = [
        ("Total", summary.total, c["on_surface_variant"], 100),
        ("Passed", summary.passed, c["secondary"], round(summary.passed / total * 100)),
        ("Failed", summary.failed, c["error"], round(summary.failed / total * 100)),
        ("Errors", summary.errored, c["tertiary"], round(summary.errored / total * 100)),
        ("Skipped", summary.skipped, c["outline"], round(summary.skipped / total * 100)),
    ]
    for label, value, color, bar_pct in cards:
        parts.append(
            f'<div class="card" style="border-left-color:{color}">'
            f'<div class="card-label" style="color:{color}">{label}</div>'
            f'<div class="card-value" style="color:{color}">{value}</div>'
            f'<div class="card-bar">'
            f'<div class="card-bar-fill" style="width:{bar_pct}%;background:{color}"></div>'
            f"</div>"
            f"</div>"
        )
    parts.append("</div>")

    # Donut
    parts.append(_donut_chart(summary.passed, summary.failed, summary.errored, summary.skipped))
    parts.append("</div>")  # summary-grid

    # Failure Groups
    failures = [r for r in summary.results if r.outcome in (TestOutcome.FAILED, TestOutcome.ERROR)]

    if failures:
        by_fp: dict[str, list] = {}
        for f in failures:
            fp = f.fingerprint or "no-fingerprint"
            by_fp.setdefault(fp, []).append(f)

        unique_fps = len({f.fingerprint for f in failures if f.fingerprint})
        parts.append(
            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">'
            f"<h2>"
            f'<span style="color:{c["error"]}">&#x26A0;</span> '
            f"Failure Groups "
            f'<span class="text-muted text-sm">({len(failures)} instance(s) across {unique_fps} pattern(s))</span>'
            f"</h2></div>"
        )

        for fp, tests in by_fp.items():
            fp_display = _escape(fp[:8]) if fp != "no-fingerprint" else "none"

            fail_count = sum(1 for t in tests if t.outcome == TestOutcome.FAILED)
            error_count = sum(1 for t in tests if t.outcome == TestOutcome.ERROR)
            is_error_group = error_count > 0 and fail_count == 0
            variant = "error" if is_error_group else "fail"

            # Count badge
            if fail_count and error_count:
                count_badge = (
                    f'<span class="fp-count fp-count-fail">{fail_count} Failure(s)</span> '
                    f'<span class="fp-count fp-count-error">{error_count} Error(s)</span>'
                )
            elif error_count:
                count_badge = f'<span class="fp-count fp-count-error">{error_count} Error(s)</span>'
            else:
                count_badge = f'<span class="fp-count fp-count-fail">{fail_count} Failure(s)</span>'

            first_msg = tests[0].error_message or "Unknown error"
            if len(first_msg) > 80:
                first_msg = first_msg[:77] + "..."

            parts.append('<div class="fp-group">')
            parts.append(
                f'<div class="fp-header">'
                f'<div class="fp-header-left">'
                f'<span class="fp-id">ID: {fp_display}</span>'
                f'<span class="fp-title">{_escape(first_msg)}</span>'
                f"</div>"
                f"<div>{count_badge}</div>"
                f"</div>"
            )

            # Affected tests
            parts.append('<div class="fp-body">')
            parts.append('<div class="fp-label">Affected Tests</div>')
            parts.append('<div class="fp-tests">')
            for t in tests:
                t_variant = "error" if t.outcome == TestOutcome.ERROR else "fail"
                icon = _ICON_ERROR if t_variant == "error" else _ICON_CLOSE
                parts.append(
                    f'<div class="fp-test fp-test-{t_variant}">'
                    f'<span class="fp-test-icon-{t_variant}">{icon}</span>'
                    f"{_escape(t.fqn)}"
                    f"</div>"
                )
            parts.append("</div>")

            # Error snippet
            snippet_test = next((t for t in tests if t.stacktrace), None)
            if snippet_test and snippet_test.stacktrace:
                trace_lines = snippet_test.stacktrace.strip().split("\n")
                preview = "\n".join(trace_lines[:4])
                parts.append(
                    f'<div class="fp-snippet fp-snippet-{variant}">'
                    f'<div class="fp-snippet-label fp-snippet-label-{variant}">Error Message Snippet</div>'
                    f"<code>{_escape(preview)}</code>"
                    f"</div>"
                )

            parts.append("</div>")  # fp-body
            parts.append("</div>")  # fp-group

    parts.append("</main>")
    return _html_shell("Test Run Summary", "\n".join(parts))
