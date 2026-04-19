"""Unit tests for the AI investigator."""
import json
import subprocess

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from flakydetector.models import InvestigationResult, RunSummary, TestOutcome, TestResult
from flakydetector.store import Store


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


# ---------------------------------------------------------------------------
# Tool function tests
# ---------------------------------------------------------------------------

from flakydetector.investigator import (
    tool_test_history,
    tool_fingerprint_group,
    tool_run_metadata,
    tool_failure_timing,
    tool_recent_commits,
    tool_test_source,
    tool_code_under_test,
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
