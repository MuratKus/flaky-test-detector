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
            if line and not line[0].isspace() and line.startswith(("def ", "class ", "@")):
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


# ---------------------------------------------------------------------------
# investigate() entry point
# ---------------------------------------------------------------------------

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

    if fingerprint is None:
        history = store.get_test_history(test_name, limit=10)
        candidates = [r["fingerprint"] for r in history if r.get("fingerprint")]
        fingerprint = candidates[0] if candidates else "unknown"

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
