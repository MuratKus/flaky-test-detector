# flaky-test-detector

[![CI](https://github.com/MuratKus/flaky-test-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/MuratKus/flaky-test-detector/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

Parse CI test artifacts, fingerprint failures by stacktrace, and detect flaky tests across runs.

**What it does:**
- Parses JUnit XML, Allure JSON, and plain CI logs (Gradle, pytest, etc.)
- Normalizes stacktraces (strips line numbers, timestamps, UUIDs, memory addresses) and hashes them to group failures by root cause
- Tracks test outcomes across runs in SQLite to detect non-deterministic tests
- Outputs JSON (pipeable), Markdown (PR comments), HTML (self-contained reports with SVG charts), or plain text

## Install

```bash
pip install -e .
```

## Quick Start

### One-shot report (no history needed)

```bash
# Parse a JUnit XML file and see failures grouped by root cause
flaky-detect report build/test-results/

# Same thing, but as markdown for a PR comment
flaky-detect report build/test-results/ --format markdown

# Generate a self-contained HTML report with SVG charts
flaky-detect report build/test-results/ --format html > report.html
```

### Track flakiness across runs

```bash
# After each CI run, ingest the results
flaky-detect ingest build/test-results/ --run-id "$GITHUB_RUN_ID"

# After a few runs, analyze for flaky tests
flaky-detect analyze

# Get the quarantine list as JSON for downstream tooling
flaky-detect analyze --format json
```

### Inspect specific tests and root causes

```bash
# See pass/fail history for a specific test
flaky-detect history com.example.LoginTest.testLoginTimeout

# See top failure root causes grouped by stacktrace fingerprint
flaky-detect fingerprints
```

## HTML Report Preview

The HTML report is a self-contained dark-themed page with SVG charts, pass/fail bars, and failure groups. It includes inline search filtering and JSON export.

> [View sample flaky analysis report](https://htmlpreview.github.io/?https://github.com/MuratKus/flaky-test-detector/blob/main/docs/sample-report-flaky.html) ·
> [View sample run summary report](https://htmlpreview.github.io/?https://github.com/MuratKus/flaky-test-detector/blob/main/docs/sample-report-run.html)

<!-- To add screenshots: open the sample reports in a browser, take screenshots, save to docs/, and uncomment: -->
<!-- ![Flaky Analysis Report](docs/screenshot-flaky.png) -->
<!-- ![Run Summary Report](docs/screenshot-run.png) -->

## Example Output

### One-shot report

```
$ flaky-detect report build/test-results/

=== sample_junit.xml (junit_xml) ===
Total: 7 | ✓3 ✗2 ⚠1 ⊘1
Failures: 3 (3 unique root cause(s))

  [e71ea007e8df4c5a] 1 test(s):
    - com.example.LoginTest.testLoginTimeout: Expected response within 5000ms

  [dd8a3edadd6d6907] 1 test(s):
    - com.example.CartTest.testCheckout: NullPointerException at CartService

  [28aba236fcfa3c18] 1 test(s):
    - com.example.CartTest.testPaymentGateway: Connection refused
```

### Flakiness analysis

```
$ flaky-detect analyze

1 flaky test(s) detected:

  🚨 com.example.LoginTest.testLoginTimeout
     flakiness=67%  runs=3  pass/fail=1/2  → quarantine
     fingerprints: e71ea007e8df4c5a
```

```bash
# Customize flakiness thresholds
flaky-detect analyze --threshold 0.3 --quarantine-at 0.7 --investigate-at 0.4
```

### Failure fingerprints

```
$ flaky-detect fingerprints

Top failure root causes (3 distinct):

  [dd8a3edadd6d] 3 occurrence(s) across 1 test(s)
    sample: NullPointerException at CartService
    - com.example.CartTest.testCheckout

  [28aba236fcfa] 2 occurrence(s) across 1 test(s)
    sample: Connection refused
    - com.example.CartTest.testPaymentGateway

  [e71ea007e8df] 2 occurrence(s) across 1 test(s)
    sample: Expected response within 5000ms
    - com.example.LoginTest.testLoginTimeout
```

## Supported Formats

| Format | Auto-detected by | Notes |
|--------|-----------------|-------|
| JUnit XML | `.xml` with `<testsuites>` or `<testsuite>` root | GitHub Actions, Gradle, Maven, pytest --junitxml |
| Allure JSON | `.json` with `status` + `name` fields | Allure results directory |
| Plain logs | Regex patterns in text files | Gradle stdout, pytest output |

The parser auto-detects the format. Point it at a file or directory and it figures it out.

## How Fingerprinting Works

Stacktraces contain volatile information that changes between runs even when the root cause is identical: line numbers shift after code changes, timestamps differ, UUIDs and memory addresses are random.

The fingerprinter normalizes all of this before hashing:

```
# Before normalization
java.lang.NullPointerException
    at com.example.CartService.getItems(CartService.java:88)
    at com.example.CartTest.testCheckout(CartTest.java:67)

# After normalization (line numbers → _, timestamps → TIMESTAMP, etc.)
java.lang.NullPointerException
    at com.example.CartService.getItems(CartService.java:_)
    at com.example.CartTest.testCheckout(CartTest.java:_)

# Fingerprint: sha256(normalized)[:16] → "dd8a3edadd6d6907"
```

This means "47 failures across 3 runs are actually 2 distinct bugs" — useful signal when you're drowning in test results.

## How Flakiness Detection Works

A test is **flaky** if it non-deterministically passes and fails across runs. The flakiness rate is calculated as:

```
flakiness = 1.0 - abs(pass_rate - 0.5) * 2
```

- 50% pass rate → flakiness 1.0 (maximally flaky — coin flip)
- 100% pass rate → flakiness 0.0 (stable pass)
- 0% pass rate → flakiness 0.0 (consistently broken, not flaky)
- 80% pass rate → flakiness 0.4

Tests are classified by recommended action:

| Flakiness | Action | Meaning |
|-----------|--------|---------|
| ≥ 0.5 | 🚨 quarantine | Remove from blocking CI gates |
| ≥ 0.3 | 🔍 investigate | Needs debugging attention |
| ≥ 0.2 | 👀 monitor | Keep watching |
| < 0.2 | — | Not flagged |

## Use in GitHub Actions

### Basic: report flaky tests in step summary

```yaml
- name: Run tests
  run: ./gradlew test --continue || true

- name: Ingest test results
  run: flaky-detect ingest build/test-results/ --run-id "${{ github.run_id }}"

- name: Check for flaky tests
  run: |
    flaky-detect analyze --format markdown >> $GITHUB_STEP_SUMMARY
```

### CI gate: fail the build if flaky tests are found

```yaml
- name: Detect flaky tests
  id: flaky
  run: |
    flaky-detect analyze --format json > /tmp/flaky.json
    COUNT=$(python -c "import json; print(json.load(open('/tmp/flaky.json'))['total_flaky'])")
    echo "count=$COUNT" >> $GITHUB_OUTPUT

- name: Fail if flaky tests exceed threshold
  if: steps.flaky.outputs.count > 0
  run: |
    echo "::error::${{ steps.flaky.outputs.count }} flaky test(s) detected"
    exit 1
```

### Auto-quarantine: skip flaky tests in CI

```yaml
- name: Generate quarantine list
  run: flaky-detect quarantine --format pytest -o conftest_quarantine.py

- name: Run tests (flaky tests auto-skipped)
  run: pytest --confcutdir=. -c conftest_quarantine.py
```

### HTML report as build artifact

```yaml
- name: Generate HTML report
  run: flaky-detect analyze --format html -o flaky-report.html --ci-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"

- name: Upload report
  uses: actions/upload-artifact@v4
  with:
    name: flaky-test-report
    path: flaky-report.html
```

### Using the composite action

```yaml
- uses: MuratKus/flaky-test-detector@main
  with:
    path: build/test-results/
    mode: analyze
    comment-on-pr: true
    upload-html-artifact: true
```

## Architecture

```
src/flakydetector/
├── cli.py              # Click-based CLI entry point
├── models.py           # TestResult, RunSummary, FlakyTest dataclasses
├── fingerprint.py      # Stacktrace normalization + hashing
├── analyzer.py         # Flakiness detection from historical data
├── store.py            # SQLite persistence layer
├── parsers/
│   ├── __init__.py     # BaseParser interface
│   ├── junit_xml.py    # JUnit XML parser
│   ├── allure_json.py  # Allure JSON results parser
│   └── plain_log.py    # Plain text log parser (Gradle, pytest, etc.)
└── reporters/
    ├── json_report.py  # JSON output (pipeable)
    ├── markdown.py     # Markdown output (PR comments)
    └── html_report.py  # HTML output (self-contained with SVG charts)
```

## Development

```bash
uv sync
uv run pytest tests/ -v
uv run ruff check .
```

## License

MIT
