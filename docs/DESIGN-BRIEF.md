# Design Brief: flaky-test-detector HTML Reports

## What is this tool?
A Python CLI that parses CI test artifacts (JUnit XML, Allure JSON, CI logs), fingerprints failures by stacktrace, and detects flaky tests across runs. It outputs self-contained single-file HTML reports (inline CSS, no external deps).

## Who uses it?
- **Primary**: Backend/platform engineers debugging CI failures on teams of 5-50
- **Secondary**: Engineering managers reviewing test health dashboards
- **Context**: Opened from a CI job link, GitHub PR comment, or a Slack bot posting the report. Typically viewed once per CI run or weekly review.

## Constraints
- **Single HTML file** — all CSS must be inline (no external stylesheets, no JS frameworks)
- **No JavaScript required** — charts are inline SVG, not canvas/JS libraries
- **Must be readable** in GitHub artifact preview, browser, and email-embedded contexts
- **Print-friendly** would be a bonus
- **Dark mode optional** but developer-friendly tools tend to default dark

## Report 1: Test Run Summary
Shows results from a single CI run. Components:

| Component | Data | Current Implementation |
|-----------|------|----------------------|
| Header | Run ID, source format (e.g. "junit_xml"), timestamp | Plain text line |
| Summary cards | Total, Passed, Failed, Errors, Skipped (counts) | 5 cards in a flex row |
| Outcome donut | Same counts as visual ratio | SVG donut chart (160x160) |
| Failure groups | Grouped by fingerprint hash. Each group: hash code, count, list of test FQNs with error message snippet (≤80 chars) | White cards with `<ul>` inside |

**Sample data** (use these exact numbers for mockup):
- Run: `ci-run-4287`, Source: `junit_xml`
- 29 total: 23 passed, 3 failed, 1 error, 2 skipped
- 4 failure groups, each with 1 test

## Report 2: Flaky Test Analysis
Shows tests detected as flaky across multiple runs. Components:

| Component | Data | Current Implementation |
|-----------|------|----------------------|
| Header | Count of flaky tests detected | "8 flaky test(s) detected" |
| Flakiness bar chart | Horizontal bars, one per test. Bar length = flakiness %. Color: red (≥50%), orange (≥30%), blue (≥20%) | SVG bar chart (780xN) |
| Flaky test table | Columns: Test name (FQN), Flakiness %, Runs, Pass/Fail counts, Action badge | HTML table |
| Action badges | quarantine (red), investigate (orange), monitor (blue) | Colored pill badges |

**Sample data** (use these for mockup):
- 8 flaky tests
- Flakiness rates: 100%, 67%, 60%, 60%, 50%, 40%, 40%, 40%
- 5 quarantine, 3 investigate
- Test names are Java FQNs, e.g. `com.acme.auth.LoginServiceTest.testLoginTimeout`

## Design direction to explore
_Fill in your preferences below before submitting to a design tool:_

- **Color palette**: [ ] Dark theme (zinc/slate bg, bright accents) / [ ] Light theme (current) / [ ] ___
- **Typography**: Monospace for test names, sans-serif for labels? Or all mono for a "terminal" feel?
- **Density**: [ ] Compact (info-dense, minimal whitespace) / [ ] Spacious (current) / [ ] ___
- **Chart style**: [ ] Keep SVG donut+bars / [ ] Replace with different visualization / [ ] ___
- **Inspiration/vibe**: _e.g. "GitHub Actions summary", "Grafana dashboard", "Linear issue tracker", "Datadog", etc._
- **Brand color (accent)**: _e.g. a specific hex, or "match my company brand"_

## Files to reference
- Current run report: `docs/sample-report-run.html`
- Current flaky report: `docs/sample-report-flaky.html`
- Report generator (Python, shows data model): `src/flakydetector/reporters/html_report.py`
