# Flaky Test Detector — Execution Plan for Claude Code

## What Exists (from this chat)

A working Python CLI skeleton with:
- 3 parsers (JUnit XML, Allure JSON, plain text logs)
- Stacktrace fingerprinting with normalization
- SQLite history tracking
- Flakiness detection with quarantine recommendations
- JSON + Markdown reporters
- 24 passing tests
- Click-based CLI

**Honest assessment of gaps:**
- Plain log parser is fragile (3 regex patterns, will break on real logs)
- No type checking, no linting config
- No integration tests (subprocess-level CLI testing)
- Fingerprinting not battle-tested against real-world traces
- No HTML report
- No GitHub Action wrapper
- No `CLAUDE.md` for future development
- Uses `pip install -e .` instead of modern `uv` tooling


---

## Tooling Setup

### Skills (installed globally via skills.sh)

You already have `find-skills` globally — this lets Claude Code search skills.sh
on the fly when it encounters unfamiliar tasks. It may pull in additional skills
automatically during development.

```bash
# The one skill that directly helps this project:
npx skills add trailofbits/skills --skill modern-python
```

**What `modern-python` gives you:** uv for dependency management, ruff for
linting/formatting, ty for type checking, proper pyproject.toml structure with
`[dependency-groups]`, Makefile patterns. It replaces the manual pip/setuptools
setup in the skeleton.

**What `find-skills` gives you:** Claude Code can self-serve additional skills
from skills.sh when it hits something it needs help with (e.g. a pytest skill,
a GitHub Actions skill). You don't need to pre-install anything else.

### CLAUDE.md (drop this in the repo root)

This is arguably more important than any skill — it gives Claude Code persistent
project context every session.

```markdown
# CLAUDE.md

## Project: flaky-test-detector
Python CLI tool that parses CI test artifacts, fingerprints failures by stacktrace,
and detects flaky tests across runs.

## Tech Stack
- Python 3.11+, managed with uv
- CLI: click
- Storage: SQLite (via stdlib sqlite3)
- Testing: pytest + pytest-cov
- Linting: ruff
- Type checking: ty

## Architecture
- `src/flakydetector/` — main package
- `src/flakydetector/parsers/` — pluggable parsers (BaseParser interface)
- `src/flakydetector/reporters/` — output formatters
- `tests/` — pytest tests, fixtures in `tests/fixtures/`

## Development Commands
- `uv run pytest tests/ -v` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run flaky-detect --help` — CLI

## Key Design Decisions
- Parsers auto-detect format via `can_parse()` method
- Fingerprinting normalizes line numbers, timestamps, UUIDs, memory addresses before hashing
- Flakiness = 1.0 - abs(pass_rate - 0.5) * 2 (closer to 0.5 pass rate = more flaky)
- SQLite for history (single file, no server, works in CI)

## Testing Philosophy
- Every parser gets: can_parse positive/negative, parse with count assertions, parse with content assertions
- Fingerprinting: same-root-cause produces same hash, different causes produce different hashes
- Analyzer: synthetic history data to test flakiness detection
- Integration tests: run CLI as subprocess, verify exit codes and output

## Rules
- Always write failing test first (TDD)
- New parsers must implement BaseParser interface
- Keep CLI thin — business logic in modules, not in click commands
- Fixtures go in tests/fixtures/ with realistic data
```

---

## Phased Execution Plan

### Phase 1: Project Foundation (do first)
**Goal:** Modernize tooling, add quality gates

Tasks:
1. Migrate from setuptools to uv (`uv init --bare`, then `uv add` deps)
2. Add ruff config to pyproject.toml (linting + formatting)
3. Add ty for type checking
4. Add Makefile (dev, lint, format, test, check-all)
5. Add pre-commit or prek hooks
6. Update CI workflow to use uv
7. Create CLAUDE.md (above)

**Verify:** `make check-all` passes (lint + types + tests)

### Phase 2: Harden the Parsers
**Goal:** Make parsers work on real-world CI output

Tasks:
1. Collect real JUnit XML samples (grab from open-source GitHub Actions runs)
2. Collect real Allure result directories (multiple files, containers, attachments)
3. Collect real Gradle/Maven/pytest log output
4. Write failing tests with these real fixtures
5. Fix parsers to handle edge cases:
   - JUnit XML: nested testsuites, system-out/system-err, rerun data
   - Allure: container files, parameterized tests, multiple result files
   - Plain log: multiline errors, ANSI color codes, interleaved output
6. Add a pytest-style log parser pattern (the `=== FAILURES ===` block format)

**Verify:** All real-world fixtures parse correctly

### Phase 3: Battle-test Fingerprinting
**Goal:** Fingerprints actually group same root cause

Tasks:
1. Collect 20+ real stacktraces (Java, Kotlin, Python, JavaScript)
2. Create pairs that SHOULD have same fingerprint (same bug, different line numbers)
3. Create pairs that SHOULD NOT match
4. Write parameterized tests for all pairs
5. Tune normalizers (may need to handle: Kotlin coroutine traces, Python async traces, Node.js promise chains)
6. Add configurable normalization (some teams want line numbers preserved)

**Verify:** Parameterized test suite with labeled expectations

### Phase 4: Integration Tests
**Goal:** CLI works end-to-end as a subprocess

Tasks:
1. Test `flaky-detect report <file>` — verify stdout format
2. Test `flaky-detect ingest` + `flaky-detect analyze` flow
3. Test `--format json` produces valid JSON
4. Test `--format markdown` produces valid markdown
5. Test directory scanning (point at a dir with mixed files)
6. Test error cases: invalid file, empty directory, corrupt XML
7. Test `--db` flag for custom database location

**Verify:** All integration tests run as subprocess calls

### Phase 5: GitHub Action Wrapper
**Goal:** Usable as a GitHub Action step with PR comments

Tasks:
1. Create `action.yml` (composite action)
2. Inputs: path, run-id, format, db-path, comment-on-pr (bool)
3. Use `actions/github-script` to post markdown as PR comment
4. Add `$GITHUB_STEP_SUMMARY` support
5. Example workflow in README
6. Test in a real repo

**Verify:** PR comment appears with flaky test report

### Phase 6: HTML Report (nice-to-have)
**Goal:** Visual report for the portfolio site

Tasks:
1. Single-file HTML report (inline CSS/JS, no deps)
2. Show: run summary, failure table grouped by fingerprint, flakiness trend chart
3. Use Chart.js or simple SVG for the trend visualization
4. Add `--format html` to CLI
5. Can be served as GitHub Pages artifact

**Verify:** Opens in browser, looks professional

### Phase 7: Polish for Portfolio
**Goal:** GitHub repo that impresses hiring managers

Tasks:
1. Badges in README (CI status, Python version, license)
2. Contributing guide
3. Changelog
4. Example output screenshots/GIFs in README
5. PyPI publishing setup (optional)
6. Link from personal website

---

## How to Use This Plan with Claude Code

```
# Start Claude Code in the project directory
# It will auto-read CLAUDE.md for context
# The modern-python skill activates when it detects Python work
# find-skills lets it pull in additional skills as needed

# Per phase, just tell it what to work on:
"Let's work on Phase 1. Read the plan in PLAN.md."

# For phases that need real data (2 & 3):
"Let's work on Phase 2. Start by collecting real JUnit XML fixtures
from open-source GitHub Actions runs, then write failing tests."
```

### Tips for getting best results:
- **One phase at a time.** Don't ask for Phase 1-4 in one shot.
- **Commit between phases.** Give Claude Code a clean git state to start from.
- **Provide real fixtures.** The more real-world test data you give it, the better the parsers will be. Grab JUnit XML from your own CI runs or public GitHub repos.
- **Review the tests it writes.** The test quality determines the code quality.
- **Let find-skills do its thing.** If Claude Code says "I found a skill for X, should I use it?" — say yes unless it looks irrelevant.
