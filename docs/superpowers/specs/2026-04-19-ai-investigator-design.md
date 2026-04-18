# AI Investigator — Design Spec
_Date: 2026-04-19_

## Overview

An AI investigation layer that sits on top of the existing flaky-test-detector. Given a test already flagged as flaky by the statistical analyzer, the investigator pulls history from SQLite, reads relevant source from the repo, and produces an evidence-first explanation: a category, supporting facts, contradicting facts, and a suggested fix direction.

The statistical layer remains the source of truth for detection. The investigator only runs on tests already flagged.

---

## CLI Surface

```
flaky-detect investigate <test-name>
  [--fingerprint <hash>]       # restrict to one failure pattern
  [--repo-path <path>]         # default: cwd
  [--format json|markdown]     # default: markdown
  [--max-commits <n>]          # default: 20
  [--model <id>]               # default: claude-sonnet-4-6
  [--no-cache]                 # force fresh investigation
```

Exits non-zero only on tool errors (missing repo, no history, API failure). Insufficient evidence is a valid output, not an error.

---

## Architecture

### File Layout

```
src/flakydetector/
  investigator.py        # tools + Claude call + caching
  cli.py                 # add `investigate` subcommand (thin, no logic)

tests/
  test_investigator.py   # unit tests for each tool function
  eval_investigator.py   # eval script (real API, run manually)
  fixtures/
    investigator/        # synthetic SQLite snapshots + label.json per case

docs/
  decisions/
    ai-investigator.md   # decision log for deferred options
```

### `investigator.py` Internal Structure

Three logical sections in a single file:

1. **Tool functions** — pure functions querying SQLite or git, returning structured dicts. No LLM involvement.
2. **Cache layer** — `investigations` table in the existing SQLite DB. Cache key: `(fingerprint, commit_sha)`. TTL: 24h. Bypassed with `--no-cache`.
3. **`investigate()` entry point** — collects all tool outputs, builds prompt, calls Claude, writes cache, returns structured result.

---

## Data Flow

1. Cache check — resolve `commit_sha` via `git rev-parse HEAD` and get the test's most recent failure fingerprint from SQLite. Look up `(fingerprint, commit_sha)`. Return cached result if hit and within TTL.
2. Tool execution — call all 7 tools upfront, collect outputs into a structured context dict.
3. Single Claude call — pass full context + output contract. Claude returns JSON.
4. Cache write — store raw JSON result against `(fingerprint, commit_sha)`.
5. Format & return — CLI formats as markdown or JSON per `--format`.

---

## Tool Contracts

| Tool | Purpose | Source |
|---|---|---|
| `get_test_history(test_name)` | Pass/fail timeline | SQLite `results` + `runs` tables |
| `get_fingerprint_group(hash)` | Tests sharing a stacktrace fingerprint | SQLite `results` |
| `get_test_source(test_name)` | Source of the test function | Grep repo for test name |
| `get_code_under_test(test_name)` | Source of code the test exercises | Parse test source, grep callee names |
| `get_recent_commits_touching(file_path, n)` | Git log for relevant files | `git log` subprocess |
| `get_run_metadata(run_id)` | Runner info, duration, timestamp | SQLite `runs` table |
| `get_failure_timing(test_name)` | Duration distribution for pass vs fail | SQLite `results` |

Rules:
- Every tool returns structured data only. No interpretation, no claims.
- If a tool finds nothing, it returns an empty result — the gap goes into NOT SUPPORTED BY EVIDENCE.
- `get_code_under_test` is best-effort; empty result is valid.

### Parameterized Tests

Exact match only in v1 — investigate the specific variant as named in SQLite (e.g. `test_login[user1-prod]`). Grouping by base name deferred to a future flag.

---

## Cache Schema

New table added to the existing SQLite DB via `_migrate()`:

```sql
CREATE TABLE IF NOT EXISTS investigations (
    fingerprint TEXT NOT NULL,
    commit_sha  TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (fingerprint, commit_sha)
);
```

---

## Claude Prompt Design

**System prompt (static, prompt-cached):** Defines the agent role, the closed category set, output contract rules (cite sources, no invented data, use `insufficient-evidence` when evidence is thin).

**User prompt:** Labeled sections for each tool's output (`### TEST HISTORY`, `### RECENT COMMITS`, etc.), followed by instruction to produce JSON matching the output schema.

**Output schema:**
```json
{
  "category": "timing-dependent",
  "confidence": "low | medium | high",
  "evidence": [{"fact": "...", "source": "SQLite | git | source"}],
  "not_supported": ["..."],
  "suggested_fix": "..."
}
```

Structured JSON output enforced via Claude's tool-use / response format to avoid regex scraping.

Prompt caching applied to the system prompt to reduce token cost on repeated calls.

---

## Allowed Categories (Closed Set)

- `timing-dependent`
- `race-condition`
- `test-data-pollution`
- `external-dependency`
- `environment-infra`
- `genuine-regression`
- `insufficient-evidence`

---

## Output Contract

```
Test: <full test name>
Flakiness: <rate>% over <n> runs

CATEGORY (<confidence> confidence)
<category>: <one-line reason>

EVIDENCE
- <fact> [source: SQLite | git | source]

NOT SUPPORTED BY EVIDENCE
- <considered claim that isn't backed>

SUGGESTED FIX DIRECTION
<short paragraph or bullet list>
```

Rules:
- Every EVIDENCE fact must cite its source.
- If no fact supports a category above `low` confidence, use `insufficient-evidence` and state what data would be needed.
- Suggestions are directional, not prescriptive.
- The agent may not invent commits, runs, or file paths.

---

## Testing

### Unit Tests (`tests/test_investigator.py`)

- Each tool function tested independently with a real in-memory SQLite DB.
- `get_recent_commits_touching` and `get_test_source` tested against a temp git repo created in the fixture.
- Cache hit / miss / TTL / `--no-cache` behavior tested without hitting the API.
- `investigate()` entry point tested with Claude call mocked — verifies prompt structure and cache write, not LLM output quality.

### Eval Script (`tests/eval_investigator.py`)

Runs the real investigator against 15 labeled cases. Hits the real API — run manually, not part of `pytest`.

Cases:
- 8 synthetic: hand-built SQLite fixtures with known category and evidence
- 5 from existing history: real flaky tests where the cause is known
- 2 negative: tests that look flaky but aren't

Scored on:
- Category correct (exact match on closed set)
- Confidence calibration
- Evidence cites real sources only
- `insufficient-evidence` used on negatives

Pass threshold: 80% category-correct on synthetic, 60% on real, 100% on negatives.

### Fixtures (`tests/fixtures/investigator/`)

Each case: a SQLite snapshot file + `label.json` with expected category and confidence band.

---

## LLM

- v1: Anthropic Claude API (`claude-sonnet-4-6` default, overridable via `--model`)
- Pluggable abstraction planned for a future iteration (extract thin `llm.py`)

---

## Non-Goals (v1)

- Replacing or modifying the statistical detector
- Automatically applying fixes or opening PRs
- Investigating consistently failing tests
- Real-time investigation during CI runs
- Cross-repo investigation
- Integration with HTML/markdown reporters (standalone CLI only)
- Parameterized test grouping
- GitHub Action wrapper, Slack integration, web UI
