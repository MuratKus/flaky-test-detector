# Flaky Test Detector — Execution Plan

## Completed Phases

### ✅ Phase 1: Project Foundation
Migrated to uv, added ruff + ty, Makefile, CI workflow.
Commit: `7984b02`

### ✅ Phase 2: Harden the Parsers
Added 30+ tests with real-world edge cases for all three parsers.
Commit: `6c4746c`

### ✅ Phase 3: Battle-test Fingerprinting
18 parameterized trace pairs (Java, Kotlin, Python, JS, Go, Ruby, C#).
Commit: `16a132c`

### ✅ Phase 4: Integration Tests
CLI subprocess tests for report, ingest, analyze, history, fingerprints commands.
Commit: `25bc059` (bundled with Phase 5)

### ✅ Phase 5: GitHub Action Wrapper
Composite action with PR comments, step summaries, artifact upload.
Commit: `25bc059`

### ✅ Phase 6: HTML Report
Self-contained HTML report with SVG charts, wired into CLI.
Commits: `359b7f1`, `1798e1e`, `7765d51`

---

## Phase 7: Polish for Portfolio (in progress)

### 7a: Sample Report & Visuals
- [x] Generate sample HTML reports from demo fixtures (`scripts/generate_sample_reports.py`)
- [x] Sample reports in `docs/` (run summary + flaky analysis)
- [ ] Add a screenshot/preview image of the HTML report to README
- [ ] Add terminal output examples (CLI screenshot or styled code blocks)
- [ ] **[Human]** Redesign HTML report styling (AI design studio — v0, Figma, etc.)
  - [ ] **[Human]** Second design pass: remove sidebar nav, "Re-Run Job" button, "Share Report", "Clear All" (not possible in static HTML)
  - [ ] Implement dark theme with slate/green/red palette from design
  - [ ] Add health score metric to reports (passed/total for run, non-flaky/total for analysis)
  - [ ] Add inline JS: test name filter/search in flaky table
  - [ ] Add inline JS: "Export JSON" button (serialize page data to download)
  - [ ] Add "View in CI" link placeholder (optional `--ci-url` CLI flag)

### 7b: Improvement Ideas
- [x] Configurable thresholds (`--threshold`, `--quarantine-at`, `--investigate-at` CLI flags)
- [ ] Trend tracking (flakiness over time, not just current snapshot)
- [ ] CI artifact auto-upload in the GitHub Action
- [ ] PyPI-ready packaging (`uv build` + publish workflow)
- [ ] Contributing guide
- [ ] Changelog

---

## How to Use This Plan with Claude Code

```
# Per phase, just tell it what to work on:
"Let's work on Phase 7a. Generate sample report visuals."

# For improvements:
"Let's tackle configurable thresholds from 7b."
```

### Tips for getting best results:
- **One phase at a time.** Don't ask for Phase 1-4 in one shot.
- **Commit between phases.** Give Claude Code a clean git state to start from.
- **Provide real fixtures.** The more real-world test data you give it, the better the parsers will be. Grab JUnit XML from your own CI runs or public GitHub repos.
- **Review the tests it writes.** The test quality determines the code quality.
- **Let find-skills do its thing.** If Claude Code says "I found a skill for X, should I use it?" — say yes unless it looks irrelevant.
