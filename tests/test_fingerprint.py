"""Tests for fingerprinting."""

from flakydetector.fingerprint import fingerprint, fingerprint_results, normalize_stacktrace
from flakydetector.models import TestOutcome, TestResult


class TestFingerprinting:
    def test_same_trace_different_line_numbers(self):
        trace1 = "java.lang.NullPointerException\n\tat com.Foo.bar(Foo.java:42)"
        trace2 = "java.lang.NullPointerException\n\tat com.Foo.bar(Foo.java:99)"
        assert fingerprint(trace1) == fingerprint(trace2)

    def test_different_exceptions_different_fingerprint(self):
        trace1 = "java.lang.NullPointerException\n\tat com.Foo.bar(Foo.java:42)"
        trace2 = "java.lang.IllegalStateException\n\tat com.Baz.qux(Baz.java:42)"
        assert fingerprint(trace1) != fingerprint(trace2)

    def test_normalizes_timestamps(self):
        t = normalize_stacktrace("Error at 2024-01-15T10:30:00Z in module")
        assert "2024-01-15" not in t
        assert "TIMESTAMP" in t

    def test_normalizes_uuids(self):
        t = normalize_stacktrace("Session a1b2c3d4-e5f6-7890-abcd-ef1234567890 failed")
        assert "a1b2c3d4" not in t
        assert "UUID" in t

    def test_empty_input(self):
        assert fingerprint(None) == ""
        assert fingerprint("") == ""
        assert fingerprint("   ") == ""

    def test_fingerprint_results_adds_fingerprints(self):
        results = [
            TestResult(
                name="t1",
                classname="C",
                outcome=TestOutcome.FAILED,
                stacktrace="java.lang.Error\n\tat X.y(X.java:1)",
            ),
            TestResult(name="t2", classname="C", outcome=TestOutcome.PASSED),
        ]
        fingerprint_results(results)
        assert results[0].fingerprint  # has a fingerprint
        assert results[1].fingerprint is None  # no stacktrace, no fingerprint
