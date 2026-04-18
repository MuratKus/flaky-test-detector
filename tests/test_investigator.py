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
