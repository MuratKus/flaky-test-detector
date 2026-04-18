# AI Investigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `flaky-detect investigate <test-name>` command that uses Claude to produce an evidence-first explanation of why a flaky test fails.

**Architecture:** A single `investigator.py` module holds 7 pure tool functions (SQLite + git + source), a cache layer backed by a new `investigations` SQLite table, and an `investigate()` entry point that gathers all tool outputs, makes one Claude API call with prompt caching, and returns a structured `InvestigationResult`. The CLI command in `cli.py` stays thin — it calls `investigate()` and formats the output.

**Tech Stack:** Python 3.11+, anthropic SDK, sqlite3 (stdlib), subprocess (git), ast (stdlib), click

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/flakydetector/models.py` | Modify | Add `InvestigationResult` dataclass |
| `src/flakydetector/store.py` | Modify | Add cache table migration + 5 new query methods |
| `src/flakydetector/investigator.py` | Create | Tool functions + `investigate()` entry point |
| `src/flakydetector/cli.py` | Modify | Add `investigate` subcommand |
| `tests/test_investigator.py` | Create | Unit tests for all tool functions + cache + wiring |
| `tests/eval_investigator.py` | Create | Eval script (hits real API — run manually) |
| `tests/fixtures/investigator/` | Create | Fixture factory functions used by eval script |

---

## Task 1: Add anthropic dependency + InvestigationResult model

**Files:**
- Modify: `src/flakydetector/models.py`

- [ ] **Step 1: Add anthropic as a dependency**

```bash
uv add anthropic
```

Expected: `pyproject.toml` updated with `anthropic` in dependencies.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_investigator.py` (create the file):

```python
"""Unit tests for the AI investigator."""
from flakydetector.models import InvestigationResult


def test_investigation_result_defaults():
    result = InvestigationResult(
        test_name="TestClass.test_foo",
        category="timing-dependent",
        confidence="high",
        evidence=[{"fact": "slow on CI", "source": "SQLite"}],
        not_supported=["race condition not found"],
        suggested_fix="Raise timeout to 10s",
    )
    assert result.cached is False
    assert result.category == "timing-dependent"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_investigator.py::test_investigation_result_defaults -v
```

Expected: FAIL — `InvestigationResult` not defined.

- [ ] **Step 4: Add InvestigationResult to models.py**

Append to `src/flakydetector/models.py`:

```python
@dataclass
class InvestigationResult:
    """Result of an AI investigation into a flaky test."""

    test_name: str
    category: str
    confidence: str
    evidence: list[dict]
    not_supported: list[str]
    suggested_fix: str
    cached: bool = False
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_investigator.py::test_investigation_result_defaults -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/flakydetector/models.py tests/test_investigator.py pyproject.toml uv.lock
git commit -m "feat: add InvestigationResult model and anthropic dependency"
```

---

## Task 2: Store — cache table + query methods

**Files:**
- Modify: `src/flakydetector/store.py`
- Test: `tests/test_investigator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_investigator.py`:

```python
import json
import pytest
from datetime import UTC, datetime, timedelta
from flakydetector.store import Store
from flakydetector.models import RunSummary, TestResult, TestOutcome


def _make_store(tmp_path):
    return Store(tmp_path / "test.db")


def _ingest_result(store, run_id, test_name, outcome, fingerprint="", duration=1.0):
    summary = RunSummary(run_id=run_id, source="junit_xml")
    summary.add(TestResult(
        name=test_name, classname="", outcome=outcome,
        duration_sec=duration, fingerprint=fingerprint,
    ))
    store.ingest(summary)


# --- Cache ---

def test_cache_miss_returns_none(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_cached_investigation("fp1", "sha1") is None


def test_cache_round_trip(tmp_path):
    store = _make_store(tmp_path)
    data = {"category": "timing-dependent", "confidence": "high",
            "evidence": [], "not_supported": [], "suggested_fix": "raise timeout"}
    store.set_cached_investigation("fp1", "sha1", data)
    assert store.get_cached_investigation("fp1", "sha1") == data


def test_cache_expired_returns_none(tmp_path):
    store = _make_store(tmp_path)
    data = {"category": "timing-dependent", "confidence": "high",
            "evidence": [], "not_supported": [], "suggested_fix": "raise timeout"}
    store.set_cached_investigation("fp1", "sha1", data)
    old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    store.conn.execute(
        "UPDATE investigations SET created_at = ? WHERE fingerprint = ?",
        (old_time, "fp1"),
    )
    store.conn.commit()
    assert store.get_cached_investigation("fp1", "sha1", ttl_hours=24) is None


def test_cache_different_key_is_miss(tmp_path):
    store = _make_store(tmp_path)
    data = {"category": "timing-dependent", "confidence": "high",
            "evidence": [], "not_supported": [], "suggested_fix": "raise timeout"}
    store.set_cached_investigation("fp1", "sha1", data)
    assert store.get_cached_investigation("fp1", "sha2") is None


# --- get_fingerprint_group ---

def test_get_fingerprint_group_returns_matching_tests(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_foo", TestOutcome.FAILED, fingerprint="fp1")
    _ingest_result(store, "run2", "test_bar", TestOutcome.FAILED, fingerprint="fp1")
    _ingest_result(store, "run3", "test_baz", TestOutcome.FAILED, fingerprint="fp2")
    result = store.get_fingerprint_group("fp1")
    names = {r["test_name"] for r in result}
    assert names == {"test_foo", "test_bar"}


def test_get_fingerprint_group_empty(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_fingerprint_group("nonexistent") == []


# --- get_run_metadata ---

def test_get_run_metadata_returns_run(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "run42", "test_foo", TestOutcome.PASSED)
    meta = store.get_run_metadata("run42")
    assert meta is not None
    assert meta["run_id"] == "run42"
    assert meta["source"] == "junit_xml"


def test_get_run_metadata_missing_returns_none(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_run_metadata("no-such-run") is None


# --- get_failure_timing ---

def test_get_failure_timing_splits_by_outcome(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_foo", TestOutcome.PASSED, duration=1.0)
    _ingest_result(store, "run2", "test_foo", TestOutcome.PASSED, duration=2.0)
    _ingest_result(store, "run3", "test_foo", TestOutcome.FAILED, duration=10.0)
    timing = store.get_failure_timing("test_foo")
    assert "passed" in timing
    assert "failed" in timing
    assert timing["passed"]["avg_dur"] == pytest.approx(1.5)
    assert timing["failed"]["avg_dur"] == pytest.approx(10.0)


def test_get_failure_timing_no_data_returns_empty(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_failure_timing("test_nonexistent") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_investigator.py -k "cache or fingerprint_group or run_metadata or failure_timing" -v
```

Expected: Multiple FAILs — methods not defined yet.

- [ ] **Step 3: Add investigations table to Store._migrate()**

In `src/flakydetector/store.py`, add `import json` at the top, then add this table to the `executescript` in `_migrate()`:

```python
import json  # add to top of file
```

In `_migrate()`, add inside the `executescript` string (after the existing index lines):

```sql
CREATE TABLE IF NOT EXISTS investigations (
    fingerprint TEXT NOT NULL,
    commit_sha  TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (fingerprint, commit_sha)
);
```

- [ ] **Step 4: Add cache methods to Store**

Append to the `Store` class in `store.py`:

```python
def get_cached_investigation(
    self, fingerprint: str, commit_sha: str, ttl_hours: int = 24
) -> dict | None:
    row = self.conn.execute(
        """SELECT result_json, created_at FROM investigations
           WHERE fingerprint = ? AND commit_sha = ?""",
        (fingerprint, commit_sha),
    ).fetchone()
    if not row:
        return None
    created_at = datetime.fromisoformat(row["created_at"])
    age_seconds = (datetime.now(UTC) - created_at).total_seconds()
    if age_seconds > ttl_hours * 3600:
        return None
    return json.loads(row["result_json"])

def set_cached_investigation(
    self, fingerprint: str, commit_sha: str, result: dict
) -> None:
    self.conn.execute(
        """INSERT OR REPLACE INTO investigations
           (fingerprint, commit_sha, result_json, created_at)
           VALUES (?, ?, ?, ?)""",
        (fingerprint, commit_sha, json.dumps(result), datetime.now(UTC).isoformat()),
    )
    self.conn.commit()
```

- [ ] **Step 5: Add get_fingerprint_group, get_run_metadata, get_failure_timing to Store**

Append to the `Store` class:

```python
def get_fingerprint_group(self, fingerprint: str) -> list[dict]:
    rows = self.conn.execute(
        """SELECT DISTINCT test_name, run_id, outcome, error_message
           FROM results
           WHERE fingerprint = ?
           ORDER BY run_id DESC
           LIMIT 50""",
        (fingerprint,),
    ).fetchall()
    return [dict(row) for row in rows]

def get_run_metadata(self, run_id: str) -> dict | None:
    row = self.conn.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row else None

def get_failure_timing(self, test_name: str) -> dict:
    rows = self.conn.execute(
        """SELECT outcome,
                  AVG(duration_sec) as avg_dur,
                  MIN(duration_sec) as min_dur,
                  MAX(duration_sec) as max_dur,
                  COUNT(*) as count
           FROM results
           WHERE test_name = ? AND outcome IN ('passed', 'failed', 'error')
           GROUP BY outcome""",
        (test_name,),
    ).fetchall()
    return {row["outcome"]: dict(row) for row in rows}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_investigator.py -k "cache or fingerprint_group or run_metadata or failure_timing" -v
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add src/flakydetector/store.py tests/test_investigator.py
git commit -m "feat: add investigation cache and query methods to Store"
```

---

## Task 3: investigator.py — 7 tool functions

**Files:**
- Create: `src/flakydetector/investigator.py`
- Test: `tests/test_investigator.py`

The 4 SQLite-backed tools wrap Store methods; the 3 git/source tools use subprocess + stdlib `ast`.

- [ ] **Step 1: Write failing tests for SQLite-backed tools**

Append to `tests/test_investigator.py`:

```python
from flakydetector.investigator import (
    tool_test_history,
    tool_fingerprint_group,
    tool_run_metadata,
    tool_failure_timing,
)


def test_tool_test_history_returns_structured(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_foo", TestOutcome.PASSED)
    _ingest_result(store, "run2", "test_foo", TestOutcome.FAILED)
    result = tool_test_history(store, "test_foo")
    assert result["total"] == 2
    assert len(result["runs"]) == 2
    outcomes = {r["outcome"] for r in result["runs"]}
    assert outcomes == {"passed", "failed"}


def test_tool_test_history_unknown_test(tmp_path):
    store = _make_store(tmp_path)
    result = tool_test_history(store, "test_nonexistent")
    assert result["total"] == 0
    assert result["runs"] == []


def test_tool_fingerprint_group_returns_tests(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_foo", TestOutcome.FAILED, fingerprint="fp1")
    result = tool_fingerprint_group(store, "fp1")
    assert result["fingerprint"] == "fp1"
    assert len(result["tests"]) == 1


def test_tool_run_metadata_returns_dict(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "myrun", "test_foo", TestOutcome.PASSED)
    result = tool_run_metadata(store, "myrun")
    assert result["run_id"] == "myrun"
    assert result["source"] == "junit_xml"


def test_tool_run_metadata_missing(tmp_path):
    store = _make_store(tmp_path)
    result = tool_run_metadata(store, "no-such-run")
    assert result == {}


def test_tool_failure_timing_returns_stats(tmp_path):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_foo", TestOutcome.PASSED, duration=1.0)
    _ingest_result(store, "run2", "test_foo", TestOutcome.FAILED, duration=9.0)
    result = tool_failure_timing(store, "test_foo")
    assert "passed" in result
    assert "failed" in result
    assert result["passed"]["avg_dur"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_investigator.py -k "tool_test_history or tool_fingerprint or tool_run_metadata or tool_failure_timing" -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create investigator.py with SQLite-backed tool functions**

Create `src/flakydetector/investigator.py`:

```python
"""AI investigator: tool functions, cache logic, and investigate() entry point."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flakydetector.store import Store


# ---------------------------------------------------------------------------
# SQLite-backed tool functions
# ---------------------------------------------------------------------------

def tool_test_history(store: "Store", test_name: str) -> dict:
    rows = store.get_test_history(test_name)
    return {
        "test_name": test_name,
        "runs": [
            {
                "run_id": r["run_id"],
                "outcome": r["outcome"],
                "fingerprint": r["fingerprint"],
                "ingested_at": r["ingested_at"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


def tool_fingerprint_group(store: "Store", fingerprint: str) -> dict:
    tests = store.get_fingerprint_group(fingerprint)
    return {"fingerprint": fingerprint, "tests": tests, "count": len(tests)}


def tool_run_metadata(store: "Store", run_id: str) -> dict:
    meta = store.get_run_metadata(run_id)
    return meta if meta else {}


def tool_failure_timing(store: "Store", test_name: str) -> dict:
    return store.get_failure_timing(test_name)
```

- [ ] **Step 4: Run SQLite tool tests to verify they pass**

```bash
uv run pytest tests/test_investigator.py -k "tool_test_history or tool_fingerprint or tool_run_metadata or tool_failure_timing" -v
```

Expected: All PASS.

- [ ] **Step 5: Write failing tests for git/source tool functions**

Append to `tests/test_investigator.py`:

```python
import subprocess
from flakydetector.investigator import (
    tool_recent_commits,
    tool_test_source,
    tool_code_under_test,
)


@pytest.fixture()
def git_repo(tmp_path):
    """Minimal git repo with one test file."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)

    test_file = tmp_path / "tests" / "test_example.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "def test_login():\n"
        "    result = do_login('user', 'pass')\n"
        "    assert result is True\n"
    )
    src_file = tmp_path / "src" / "auth.py"
    src_file.parent.mkdir()
    src_file.write_text("def do_login(user, password):\n    return True\n")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_tool_recent_commits_returns_commits(git_repo):
    result = tool_recent_commits("tests/test_example.py", n=5, repo_path=git_repo)
    assert result["file_path"] == "tests/test_example.py"
    assert len(result["commits"]) >= 1
    assert "sha" in result["commits"][0]
    assert "message" in result["commits"][0]


def test_tool_recent_commits_missing_file_returns_empty(git_repo):
    result = tool_recent_commits("no/such/file.py", n=5, repo_path=git_repo)
    assert result["commits"] == []


def test_tool_test_source_finds_function(git_repo):
    result = tool_test_source("test_login", repo_path=git_repo)
    assert result["file"] is not None
    assert "def test_login" in result["source"]


def test_tool_test_source_not_found(git_repo):
    result = tool_test_source("test_nonexistent", repo_path=git_repo)
    assert result["source"] is None


def test_tool_code_under_test_finds_callee(git_repo):
    result = tool_code_under_test("test_login", repo_path=git_repo)
    assert "do_login" in result["callees"]
```

- [ ] **Step 6: Run git/source tool tests to verify they fail**

```bash
uv run pytest tests/test_investigator.py -k "recent_commits or test_source or code_under_test" -v
```

Expected: FAIL — functions not defined.

- [ ] **Step 7: Add git/source tool functions to investigator.py**

Append to `src/flakydetector/investigator.py`:

```python
# ---------------------------------------------------------------------------
# Git / source-backed tool functions
# ---------------------------------------------------------------------------

_SKIP_CALLEES = {
    "assert", "assertEqual", "assertTrue", "assertFalse", "assertIn",
    "assertIsNone", "assertIsNotNone", "assertRaises", "setUp", "tearDown",
    "mock", "patch", "MagicMock", "call", "ANY", "raises", "fixture",
    "print", "len", "range", "str", "int", "list", "dict", "set", "tuple",
}


def tool_recent_commits(file_path: str, n: int = 20, repo_path: Path = Path(".")) -> dict:
    result = subprocess.run(
        ["git", "log", f"-{n}", "--oneline", "--", file_path],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    commits = []
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            if line:
                sha, _, message = line.partition(" ")
                commits.append({"sha": sha, "message": message})
    return {"file_path": file_path, "commits": commits}


def tool_test_source(test_name: str, repo_path: Path = Path(".")) -> dict:
    func_name = test_name.split(".")[-1]
    result = subprocess.run(
        ["git", "grep", "-n", "--", f"def {func_name}("],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"test_name": test_name, "source": None, "file": None, "line": None}

    first = result.stdout.splitlines()[0]
    parts = first.split(":", 2)
    if len(parts) < 3:
        return {"test_name": test_name, "source": None, "file": None, "line": None}

    file_path, line_no_str = parts[0], parts[1]
    line_no = int(line_no_str)
    full_path = Path(repo_path) / file_path
    try:
        lines = full_path.read_text(encoding="utf-8").splitlines()
        func_lines = [lines[line_no - 1]]
        for line in lines[line_no:]:
            if line and not line[0].isspace() and (
                line.startswith(("def ", "class ", "@"))
            ):
                break
            func_lines.append(line)
        return {
            "test_name": test_name,
            "source": "\n".join(func_lines),
            "file": file_path,
            "line": line_no,
        }
    except (FileNotFoundError, ValueError, IndexError):
        return {"test_name": test_name, "source": None, "file": file_path, "line": line_no}


def tool_code_under_test(test_name: str, repo_path: Path = Path(".")) -> dict:
    source_info = tool_test_source(test_name, repo_path)
    if not source_info["source"]:
        return {"test_name": test_name, "callees": [], "sources": []}

    try:
        tree = ast.parse(source_info["source"])
    except SyntaxError:
        return {"test_name": test_name, "callees": [], "sources": []}

    callees: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in _SKIP_CALLEES:
                callees.add(node.func.id)
            elif isinstance(node.func, ast.Attribute) and node.func.attr not in _SKIP_CALLEES:
                callees.add(node.func.attr)

    sources = []
    for callee in list(callees)[:5]:
        grep = subprocess.run(
            ["git", "grep", "-n", "--", f"def {callee}("],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if grep.returncode == 0 and grep.stdout.strip():
            matches = grep.stdout.splitlines()
            non_test = [m for m in matches if "test" not in m.lower()]
            chosen = (non_test or matches)[0]
            parts = chosen.split(":", 2)
            if len(parts) >= 2:
                sources.append({"function": callee, "location": f"{parts[0]}:{parts[1]}"})

    return {"test_name": test_name, "callees": list(callees), "sources": sources}
```

- [ ] **Step 8: Run all tool tests to verify they pass**

```bash
uv run pytest tests/test_investigator.py -k "tool_" -v
```

Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add src/flakydetector/investigator.py tests/test_investigator.py
git commit -m "feat: add investigator tool functions (SQLite + git + source)"
```

---

## Task 4: investigator.py — investigate() entry point

**Files:**
- Modify: `src/flakydetector/investigator.py`
- Test: `tests/test_investigator.py`

- [ ] **Step 1: Write failing tests for investigate()**

Append to `tests/test_investigator.py`:

```python
from unittest.mock import MagicMock, patch
from flakydetector.investigator import investigate
from flakydetector.models import InvestigationResult


def _mock_claude_response(category="timing-dependent", confidence="medium"):
    mock_content = MagicMock()
    mock_content.text = json.dumps({
        "category": category,
        "confidence": confidence,
        "evidence": [{"fact": "test took 9s on fail vs 1s on pass", "source": "SQLite"}],
        "not_supported": ["no external service calls found"],
        "suggested_fix": "Raise the timeout from 5s to 15s",
    })
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


def test_investigate_returns_result(tmp_path, git_repo):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_login", TestOutcome.PASSED, fingerprint="fp1", duration=1.0)
    _ingest_result(store, "run2", "test_login", TestOutcome.FAILED, fingerprint="fp1", duration=9.0)

    with patch("flakydetector.investigator.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = _mock_claude_response()
        result = investigate("test_login", store, repo_path=git_repo, use_cache=False)

    assert isinstance(result, InvestigationResult)
    assert result.category == "timing-dependent"
    assert result.confidence == "medium"
    assert result.cached is False


def test_investigate_writes_cache(tmp_path, git_repo):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_login", TestOutcome.FAILED, fingerprint="fp1")

    with patch("flakydetector.investigator.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = _mock_claude_response()
        investigate("test_login", store, repo_path=git_repo, use_cache=True)

    # Claude should have been called once
    assert mock_client_cls.return_value.messages.create.call_count == 1


def test_investigate_returns_cached_result(tmp_path, git_repo):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_login", TestOutcome.FAILED, fingerprint="fp1")

    cached_data = {
        "category": "race-condition", "confidence": "high",
        "evidence": [], "not_supported": [], "suggested_fix": "Add a lock",
    }
    store.set_cached_investigation("fp1", _get_head_sha(git_repo), cached_data)

    with patch("flakydetector.investigator.anthropic.Anthropic") as mock_client_cls:
        result = investigate("test_login", store, repo_path=git_repo, use_cache=True)

    mock_client_cls.return_value.messages.create.assert_not_called()
    assert result.category == "race-condition"
    assert result.cached is True


def _get_head_sha(repo_path):
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_path), capture_output=True, text=True)
    return r.stdout.strip()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_investigator.py -k "test_investigate_" -v
```

Expected: FAIL — `investigate` not defined.

- [ ] **Step 3: Add investigate() to investigator.py**

Append to `src/flakydetector/investigator.py`:

```python
import anthropic
from flakydetector.models import InvestigationResult

_SYSTEM_PROMPT = """You are a flaky test investigator. Given evidence from a CI history database, \
git repository, and source code, explain why the given test is flaky.

Rules:
- Pick exactly one category from the closed set
- Every fact in EVIDENCE must cite its source (SQLite | git | source)
- If no fact supports above low confidence, use insufficient-evidence
- Never invent commits, runs, or file paths — only use what was provided
- Suggestions are directional, not prescriptive (e.g. "raise timeout" not "change line 42")

Categories (pick exactly one):
- timing-dependent: passes or fails based on duration, latency, or sleep
- race-condition: concurrent code paths with non-deterministic ordering
- test-data-pollution: state leaks between tests
- external-dependency: flakiness traced to network, third-party service, or shared resource
- environment-infra: runner, container, or CI-environment variation
- genuine-regression: recent code change correlates with onset of failures
- insufficient-evidence: none of the above can be supported

Respond with valid JSON only:
{
  "category": "<category>",
  "confidence": "low | medium | high",
  "evidence": [{"fact": "...", "source": "SQLite | git | source"}],
  "not_supported": ["<considered claim not backed by evidence>"],
  "suggested_fix": "<short paragraph or bullet list>"
}"""


def _get_commit_sha(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _build_user_prompt(test_name: str, tool_outputs: dict) -> str:
    parts = [f"Investigate why `{test_name}` is flaky.\n"]
    for tool_name, output in tool_outputs.items():
        label = tool_name.upper().replace("_", " ")
        parts.append(f"### {label}")
        parts.append(json.dumps(output, indent=2))
        parts.append("")
    parts.append("Respond with the JSON investigation result.")
    return "\n".join(parts)


def investigate(
    test_name: str,
    store: "Store",
    repo_path: Path = Path("."),
    fingerprint: str | None = None,
    max_commits: int = 20,
    model: str = "claude-sonnet-4-6",
    use_cache: bool = True,
) -> InvestigationResult:
    repo_path = Path(repo_path)
    commit_sha = _get_commit_sha(repo_path)

    # Resolve fingerprint from most recent failure if not provided
    if fingerprint is None:
        history = store.get_test_history(test_name, limit=10)
        candidates = [r["fingerprint"] for r in history if r.get("fingerprint")]
        fingerprint = candidates[0] if candidates else "unknown"

    # Cache check
    if use_cache and fingerprint != "unknown":
        cached = store.get_cached_investigation(fingerprint, commit_sha)
        if cached:
            return InvestigationResult(
                test_name=test_name,
                category=cached["category"],
                confidence=cached["confidence"],
                evidence=cached["evidence"],
                not_supported=cached["not_supported"],
                suggested_fix=cached["suggested_fix"],
                cached=True,
            )

    # Gather tool outputs
    history_rows = store.get_test_history(test_name)
    test_source = tool_test_source(test_name, repo_path)
    tool_outputs = {
        "test_history": tool_test_history(store, test_name),
        "fingerprint_group": tool_fingerprint_group(store, fingerprint),
        "run_metadata": tool_run_metadata(store, history_rows[0]["run_id"]) if history_rows else {},
        "failure_timing": tool_failure_timing(store, test_name),
        "test_source": test_source,
        "code_under_test": tool_code_under_test(test_name, repo_path),
        "recent_commits": tool_recent_commits(
            test_source.get("file") or "", max_commits, repo_path
        ),
    }

    user_prompt = _build_user_prompt(test_name, tool_outputs)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[
            {"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    result_dict = json.loads(response.content[0].text)

    if use_cache and fingerprint != "unknown":
        store.set_cached_investigation(fingerprint, commit_sha, result_dict)

    return InvestigationResult(
        test_name=test_name,
        category=result_dict["category"],
        confidence=result_dict["confidence"],
        evidence=result_dict["evidence"],
        not_supported=result_dict["not_supported"],
        suggested_fix=result_dict["suggested_fix"],
        cached=False,
    )
```

- [ ] **Step 4: Run investigate() tests to verify they pass**

```bash
uv run pytest tests/test_investigator.py -k "test_investigate_" -v
```

Expected: All PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/flakydetector/investigator.py tests/test_investigator.py
git commit -m "feat: add investigate() entry point with Claude API and caching"
```

---

## Task 5: CLI — investigate subcommand

**Files:**
- Modify: `src/flakydetector/cli.py`
- Test: `tests/test_investigator.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_investigator.py`:

```python
from click.testing import CliRunner
from flakydetector.cli import main


def test_investigate_cli_markdown_output(tmp_path, git_repo):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_login", TestOutcome.FAILED, fingerprint="fp1")
    store.close()

    runner = CliRunner()
    with patch("flakydetector.investigator.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = _mock_claude_response()
        result = runner.invoke(
            main,
            ["--db", str(tmp_path / "test.db"), "investigate", "test_login",
             "--repo-path", str(git_repo), "--no-cache"],
        )

    assert result.exit_code == 0
    assert "CATEGORY" in result.output
    assert "timing-dependent" in result.output
    assert "EVIDENCE" in result.output
    assert "SUGGESTED FIX DIRECTION" in result.output


def test_investigate_cli_json_output(tmp_path, git_repo):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_login", TestOutcome.FAILED, fingerprint="fp1")
    store.close()

    runner = CliRunner()
    with patch("flakydetector.investigator.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = _mock_claude_response()
        result = runner.invoke(
            main,
            ["--db", str(tmp_path / "test.db"), "investigate", "test_login",
             "--repo-path", str(git_repo), "--format", "json", "--no-cache"],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["category"] == "timing-dependent"
    assert "evidence" in data


def test_investigate_cli_exits_nonzero_on_api_error(tmp_path, git_repo):
    store = _make_store(tmp_path)
    _ingest_result(store, "run1", "test_login", TestOutcome.FAILED, fingerprint="fp1")
    store.close()

    runner = CliRunner()
    with patch("flakydetector.investigator.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.side_effect = Exception("API error")
        result = runner.invoke(
            main,
            ["--db", str(tmp_path / "test.db"), "investigate", "test_login",
             "--repo-path", str(git_repo), "--no-cache"],
        )

    assert result.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_investigator.py -k "cli" -v
```

Expected: FAIL — `investigate` subcommand not registered.

- [ ] **Step 3: Add investigate subcommand to cli.py**

Add `import json` at the top of `cli.py` if not already present (it's added locally in `ingest` — move the import to the module level):

In `cli.py`, add the `investigate` command after the `fingerprints` command:

```python
@main.command()
@click.argument("test_name")
@click.option("--fingerprint", default=None, help="Restrict to one failure pattern.")
@click.option("--repo-path", default=".", type=click.Path(), help="Path to the git repository.")
@click.option(
    "--format", "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format.",
)
@click.option("--max-commits", default=20, help="Recent commits to consider.")
@click.option("--model", default="claude-sonnet-4-6", help="Claude model ID.")
@click.option("--no-cache", is_flag=True, default=False, help="Force fresh investigation.")
@click.pass_context
def investigate(ctx, test_name, fingerprint, repo_path, fmt, max_commits, model, no_cache):
    """Investigate why a flaky test fails using AI analysis."""
    import json as _json
    from flakydetector.investigator import investigate as run_investigation

    store = Store(ctx.obj["db_path"])
    try:
        result = run_investigation(
            test_name=test_name,
            store=store,
            repo_path=Path(repo_path),
            fingerprint=fingerprint,
            max_commits=max_commits,
            model=model,
            use_cache=not no_cache,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        store.close()
        raise SystemExit(1)

    if fmt == "json":
        click.echo(_json.dumps(result.__dict__, indent=2))
    else:
        cached_note = " (cached)" if result.cached else ""
        click.echo(f"Test: {result.test_name}")
        click.echo(f"\nCATEGORY ({result.confidence} confidence){cached_note}")
        click.echo(f"  {result.category}")
        click.echo("\nEVIDENCE")
        for e in result.evidence:
            click.echo(f"  - {e['fact']} [source: {e['source']}]")
        if result.not_supported:
            click.echo("\nNOT SUPPORTED BY EVIDENCE")
            for item in result.not_supported:
                click.echo(f"  - {item}")
        click.echo("\nSUGGESTED FIX DIRECTION")
        click.echo(f"  {result.suggested_fix}")

    store.close()
```

- [ ] **Step 4: Run CLI tests to verify they pass**

```bash
uv run pytest tests/test_investigator.py -k "cli" -v
```

Expected: All PASS.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All PASS.

- [ ] **Step 6: Smoke test the CLI help**

```bash
uv run flaky-detect investigate --help
```

Expected: Help text showing `investigate` command with all options listed.

- [ ] **Step 7: Commit**

```bash
git add src/flakydetector/cli.py tests/test_investigator.py
git commit -m "feat: add investigate CLI subcommand"
```

---

## Task 6: Eval fixtures

**Files:**
- Create: `tests/fixtures/investigator/fixtures.py`

Each fixture is a Python factory function that creates a populated in-memory (or temp) SQLite store, paired with a `label` dict. The eval script imports these directly — no binary SQLite files in git.

- [ ] **Step 1: Create the fixture module**

Create `tests/fixtures/investigator/fixtures.py`:

```python
"""Synthetic investigation fixtures for eval_investigator.py.

Each fixture() returns (store, test_name, label) where label = {"category": ..., "confidence": ...}.
Store is populated with history that clearly points to the expected category.
"""

from pathlib import Path
import tempfile
from flakydetector.store import Store
from flakydetector.models import RunSummary, TestResult, TestOutcome


def _store(tmp_path: Path | None = None) -> Store:
    if tmp_path is None:
        tmp = tempfile.mkdtemp()
        return Store(Path(tmp) / "eval.db")
    return Store(tmp_path / "eval.db")


def _add(store, run_id, test_name, outcome, duration=1.0, fingerprint="fp1", error_message=""):
    summary = RunSummary(run_id=run_id, source="junit_xml")
    summary.add(TestResult(
        name=test_name, classname="",
        outcome=outcome, duration_sec=duration,
        fingerprint=fingerprint, error_message=error_message,
    ))
    store.ingest(summary)


# --- Synthetic fixtures ---

def fixture_timing_dependent():
    """Test passes in <2s, consistently fails when it takes >8s (timeout scenario)."""
    store = _store()
    test = "test_payment_gateway"
    for i in range(5):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED, duration=1.2)
    for i in range(4):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED, duration=9.5,
             error_message="TimeoutError: request exceeded 5s limit")
    return store, test, {"category": "timing-dependent", "confidence": "high"}


def fixture_test_data_pollution():
    """Test fails after a specific other test runs — shared DB state."""
    store = _store()
    test = "test_user_count_is_zero"
    for i in range(4):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED, fingerprint="fp2")
    for i in range(4):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED, fingerprint="fp2",
             error_message="AssertionError: expected 0 users, got 3")
    # Same fingerprint on multiple tests signals shared state
    for i in range(4):
        _add(store, f"fail-{i}", "test_create_users", TestOutcome.FAILED, fingerprint="fp2")
    return store, test, {"category": "test-data-pollution", "confidence": "medium"}


def fixture_external_dependency():
    """Test fails with network errors pointing to a third-party service."""
    store = _store()
    test = "test_send_email_notification"
    for i in range(5):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED)
    for i in range(5):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED, fingerprint="fp3",
             error_message="ConnectionError: failed to connect to smtp.mailgun.com:587")
    return store, test, {"category": "external-dependency", "confidence": "high"}


def fixture_environment_infra():
    """Test fails on some runs with resource/memory errors, passes on others."""
    store = _store()
    test = "test_large_file_processing"
    for i in range(5):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED, duration=3.0)
    for i in range(4):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED, fingerprint="fp4",
             error_message="MemoryError: unable to allocate 2.5 GiB")
    return store, test, {"category": "environment-infra", "confidence": "medium"}


def fixture_genuine_regression():
    """Test was stable, then started failing after a commit pattern."""
    store = _store()
    test = "test_login_redirects"
    for i in range(8):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED)
    for i in range(5):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED, fingerprint="fp5",
             error_message="AssertionError: expected redirect to /dashboard, got /login")
    return store, test, {"category": "genuine-regression", "confidence": "medium"}


def fixture_insufficient_evidence_sparse_history():
    """Only 2 runs total — not enough evidence for any category."""
    store = _store()
    test = "test_obscure_edge_case"
    _add(store, "pass-1", test, TestOutcome.PASSED)
    _add(store, "fail-1", test, TestOutcome.FAILED, error_message="unknown error")
    return store, test, {"category": "insufficient-evidence", "confidence": "low"}


def fixture_race_condition():
    """Test intermittently fails with ordering errors in concurrent context."""
    store = _store()
    test = "test_concurrent_counter"
    for i in range(5):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED)
    for i in range(4):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED, fingerprint="fp6",
             error_message="AssertionError: expected counter=100, got 97 (race on increment)")
    return store, test, {"category": "race-condition", "confidence": "high"}


def fixture_negative_consistently_failing():
    """Test fails every run — this is a bug, not flakiness."""
    store = _store()
    test = "test_always_fails"
    for i in range(10):
        _add(store, f"fail-{i}", test, TestOutcome.FAILED,
             error_message="NotImplementedError: feature not built yet")
    return store, test, {"category": "insufficient-evidence", "confidence": "low"}


def fixture_negative_stable_pass():
    """Test passes every run — not flaky at all."""
    store = _store()
    test = "test_always_passes"
    for i in range(10):
        _add(store, f"pass-{i}", test, TestOutcome.PASSED)
    return store, test, {"category": "insufficient-evidence", "confidence": "low"}


ALL_FIXTURES = [
    ("timing_dependent", fixture_timing_dependent),
    ("test_data_pollution", fixture_test_data_pollution),
    ("external_dependency", fixture_external_dependency),
    ("environment_infra", fixture_environment_infra),
    ("genuine_regression", fixture_genuine_regression),
    ("insufficient_evidence_sparse", fixture_insufficient_evidence_sparse_history),
    ("race_condition", fixture_race_condition),
    ("negative_consistently_failing", fixture_negative_consistently_failing),
    ("negative_stable_pass", fixture_negative_stable_pass),
]
```

- [ ] **Step 2: Verify fixtures import cleanly**

```bash
uv run python -c "from tests.fixtures.investigator.fixtures import ALL_FIXTURES; print(len(ALL_FIXTURES), 'fixtures')"
```

Expected: `9 fixtures`

- [ ] **Step 3: Create tests/fixtures/investigator/__init__.py**

```bash
touch tests/fixtures/investigator/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/investigator/
git commit -m "feat: add synthetic eval fixtures for AI investigator"
```

---

## Task 7: Eval script

**Files:**
- Create: `tests/eval_investigator.py`

This script hits the real Claude API. It is **not** run by pytest — run manually before shipping.

- [ ] **Step 1: Create the eval script**

Create `tests/eval_investigator.py`:

```python
#!/usr/bin/env python
"""Eval script for the AI investigator.

Runs against synthetic fixtures and scores category correctness,
confidence calibration, and evidence integrity.

Usage:
    uv run python tests/eval_investigator.py

Requires ANTHROPIC_API_KEY in environment. Costs tokens.
Pass thresholds: 80% synthetic, 60% real, 100% negatives.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.fixtures.investigator.fixtures import ALL_FIXTURES
from flakydetector.investigator import investigate


def score_result(result, label: dict) -> dict:
    category_ok = result.category == label["category"]
    # Confidence calibration: high label → accept high only; low label → accept low/medium
    expected_conf = label["confidence"]
    if expected_conf == "high":
        confidence_ok = result.confidence == "high"
    elif expected_conf == "medium":
        confidence_ok = result.confidence in ("medium", "high")
    else:
        confidence_ok = True  # low label: any confidence accepted

    evidence_ok = len(result.evidence) > 0 and all(
        "source" in e and e["source"] in ("SQLite", "git", "source")
        for e in result.evidence
    )

    return {
        "category_ok": category_ok,
        "confidence_ok": confidence_ok,
        "evidence_ok": evidence_ok,
        "category_got": result.category,
        "category_expected": label["category"],
        "confidence_got": result.confidence,
    }


def main():
    print("AI Investigator Eval\n" + "=" * 40)
    results = []

    for name, factory in ALL_FIXTURES:
        store, test_name, label = factory()
        print(f"\n[{name}] investigating '{test_name}'...")
        try:
            result = investigate(test_name, store, use_cache=False)
            scores = score_result(result, label)
            status = "PASS" if scores["category_ok"] else "FAIL"
            print(f"  {status}: expected={label['category']} got={result.category} "
                  f"confidence={result.confidence}")
            results.append({"name": name, "label": label, **scores})
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"name": name, "label": label, "category_ok": False,
                            "confidence_ok": False, "evidence_ok": False, "error": str(e)})
        finally:
            store.close()

    print("\n" + "=" * 40)
    total = len(results)
    cat_pass = sum(1 for r in results if r.get("category_ok"))
    conf_pass = sum(1 for r in results if r.get("confidence_ok"))
    ev_pass = sum(1 for r in results if r.get("evidence_ok"))

    negative_names = {"negative_consistently_failing", "negative_stable_pass"}
    negative_results = [r for r in results if r["name"] in negative_names]
    synthetic_results = [r for r in results if r["name"] not in negative_names]

    neg_cat_pass = sum(1 for r in negative_results if r.get("category_ok"))
    syn_cat_pass = sum(1 for r in synthetic_results if r.get("category_ok"))

    print(f"Category correct:     {cat_pass}/{total}")
    print(f"  Synthetic:          {syn_cat_pass}/{len(synthetic_results)} (threshold: 80%)")
    print(f"  Negatives:          {neg_cat_pass}/{len(negative_results)} (threshold: 100%)")
    print(f"Confidence calibrated:{conf_pass}/{total}")
    print(f"Evidence integrity:   {ev_pass}/{total}")

    syn_pct = syn_cat_pass / len(synthetic_results) if synthetic_results else 0
    neg_pct = neg_cat_pass / len(negative_results) if negative_results else 0

    passed = syn_pct >= 0.80 and neg_pct >= 1.0
    print(f"\n{'EVAL PASSED' if passed else 'EVAL FAILED'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the script is importable and shows help**

```bash
uv run python tests/eval_investigator.py --help 2>&1 || uv run python -c "import tests.eval_investigator; print('ok')"
```

Expected: No import errors.

- [ ] **Step 3: Run the full test suite one final time**

```bash
uv run pytest tests/ -v --ignore=tests/eval_investigator.py
```

Expected: All PASS.

- [ ] **Step 4: Run ruff to verify no lint issues**

```bash
uv run ruff check src/flakydetector/investigator.py src/flakydetector/models.py src/flakydetector/store.py src/flakydetector/cli.py
```

Expected: No issues.

- [ ] **Step 5: Commit**

```bash
git add tests/eval_investigator.py
git commit -m "feat: add eval script for AI investigator quality scoring"
```

---

## Done

The AI Investigator is complete when:
- `uv run flaky-detect investigate <test-name>` runs end-to-end
- All unit tests pass
- `uv run python tests/eval_investigator.py` scores ≥ 80% synthetic, 100% negatives (requires API key)
