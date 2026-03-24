"""Stacktrace fingerprinting.

Normalizes stacktraces by stripping volatile parts (line numbers, memory
addresses, timestamps, thread IDs) and hashing the result. Two failures
with the same fingerprint share the same root cause.

This is what lets us say "these 47 failures are actually 3 distinct bugs."
"""

import hashlib
import re

# Things to strip from stacktraces before hashing
_NORMALIZERS: list[tuple[re.Pattern, str]] = [
    # Java/Kotlin line numbers: ClassName.java:42 → ClassName.java:_
    (re.compile(r"(\.(?:java|kt|scala|groovy)):\d+"), r"\1:_"),
    # Python line numbers: File "foo.py", line 42 → File "foo.py", line _
    (re.compile(r'line \d+'), "line _"),
    # Memory addresses: 0x7fff5fbff8a0 → 0x_
    (re.compile(r"0x[0-9a-fA-F]+"), "0x_"),
    # Thread IDs/names: Thread-42, pool-3-thread-1
    (re.compile(r"Thread-\d+"), "Thread-_"),
    (re.compile(r"pool-\d+-thread-\d+"), "pool-_-thread-_"),
    # Timestamps in various formats
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"), "TIMESTAMP"),
    (re.compile(r"\d{13}"), "EPOCH_MS"),  # unix millis
    # UUIDs
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "UUID"),
    # Temp file paths / session IDs
    (re.compile(r"/tmp/[\w.-]+"), "/tmp/_"),
    # Numeric IDs that vary (port numbers, PIDs, etc.)
    (re.compile(r":\d{4,5}(?=\s|$|/)"), ":_PORT"),
]


def normalize_stacktrace(raw: str) -> str:
    """Strip volatile parts from a stacktrace, preserving structure."""
    text = raw.strip()
    for pattern, replacement in _NORMALIZERS:
        text = pattern.sub(replacement, text)

    # Collapse repeated whitespace
    text = re.sub(r"[ \t]+", " ", text)
    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text


def fingerprint(raw: str | None) -> str:
    """Return a short hash fingerprint for a stacktrace.

    Returns empty string for None/empty input.
    """
    if not raw or not raw.strip():
        return ""

    normalized = normalize_stacktrace(raw)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def fingerprint_results(results: list) -> list:
    """Add fingerprints to all test results in-place and return them."""
    for r in results:
        if r.stacktrace:
            r.fingerprint = fingerprint(r.stacktrace)
    return results
