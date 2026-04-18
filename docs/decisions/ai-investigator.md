# AI Investigator — Decision Log

Decisions made during design that were deferred or rejected for v1, kept here for future reference.

---

## LLM Provider

**Decided:** Anthropic Claude API for v1, with a pluggable abstraction planned as a future iteration.

**Deferred options:**
- Local model via ollama/llama.cpp — works offline and in air-gapped CI, zero marginal cost, weaker reasoning
- Pluggable from day one — clean abstraction, more upfront complexity; planned as next iteration after v1

---

## Investigation Caching

**Decided:** Cache per `(fingerprint, commit_sha)` in SQLite with 24h TTL, bypassed by `--no-cache`.

**Considered and rejected for v1:**
- No caching — simpler but costs tokens on every call; rejected because SQLite is already present and the cache table is minimal

---

## Parameterized Test Handling

**Decided:** Exact match only in v1. Investigate the specific named variant as stored in SQLite.

**Deferred:**
- `--group-params` flag — strip `[...]` suffix and pool history across all variants of a test; deferred until real usage shows it's needed

---

## Report Integration

**Decided:** Standalone CLI only. `flaky-detect investigate` prints to stdout; no integration with existing reporters.

**Deferred options:**
- HTML report integration — "Investigate" button/link per flaky test that triggers the command
- Markdown report integration — investigation summaries appear inline in the markdown output
- These are good candidates for a v2 integration pass once the CLI is stable
