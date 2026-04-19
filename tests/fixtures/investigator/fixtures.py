"""Synthetic investigation fixtures for eval_investigator.py.

Each fixture() returns (store, test_name, label) where label = {"category": ..., "confidence": ...}.
Store is populated with history that clearly points to the expected category.
"""

import tempfile
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.store import Store


def _store() -> Store:
    tmp = tempfile.mkdtemp()
    return Store(Path(tmp) / "eval.db")


def _add(store, run_id, test_name, outcome, duration=1.0, fingerprint="fp1", error_message=""):
    summary = RunSummary(run_id=run_id, source="junit_xml")
    summary.add(TestResult(
        name=test_name, classname="",
        outcome=outcome, duration_sec=duration,
        fingerprint=fingerprint, error_message=error_message,
    ))
    store.ingest(summary)


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
