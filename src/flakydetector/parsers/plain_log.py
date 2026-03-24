"""Plain text log parser.

Extracts test results from raw CI stdout/stderr logs using common patterns:
- Gradle test output
- pytest output
- Generic PASSED/FAILED markers
- Java/Python stacktrace extraction
"""

import re
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.parsers import BaseParser

# Patterns for different test frameworks
_PATTERNS = {
    # Gradle: "com.example.MyTest > testLogin FAILED"
    "gradle": re.compile(
        r"^(?P<class>[\w.]+)\s*>\s*(?P<name>\w+)(?:\(.*?\))?\s+(?P<status>PASSED|FAILED|SKIPPED)",
        re.MULTILINE,
    ),
    # pytest: "tests/test_foo.py::test_bar PASSED"
    "pytest": re.compile(
        r"^(?P<path>[\w/._-]+)::(?P<name>\w+)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED)",
        re.MULTILINE,
    ),
    # Generic: "TEST testName ... PASSED" or "✓ testName" / "✗ testName"
    "generic": re.compile(
        r"(?:TEST|test)\s+(?P<name>[\w.]+)\s*\.{0,3}\s*(?P<status>PASS(?:ED)?|FAIL(?:ED)?|SKIP(?:PED)?|ERROR)",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Java stacktrace block
_JAVA_STACKTRACE = re.compile(
    r"((?:[\w.$]+(?:Exception|Error|Throwable)[^\n]*\n)"
    r"(?:\s+at\s+[\w.$<>]+\([\w.:]+\)\n?)+)",
    re.MULTILINE,
)

# Python traceback block
_PYTHON_TRACEBACK = re.compile(
    r"(Traceback \(most recent call last\):\n(?:\s+File .+\n\s+.+\n?)+\w+(?:Error|Exception)[^\n]*)",
    re.MULTILINE,
)

_STATUS_NORM = {
    "passed": TestOutcome.PASSED,
    "pass": TestOutcome.PASSED,
    "failed": TestOutcome.FAILED,
    "fail": TestOutcome.FAILED,
    "error": TestOutcome.ERROR,
    "skipped": TestOutcome.SKIPPED,
    "skip": TestOutcome.SKIPPED,
}


class PlainLogParser(BaseParser):

    def can_parse(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.suffix in (".xml", ".json"):
            return False
        try:
            text = path.read_text(errors="replace")[:5000]
            return any(p.search(text) for p in _PATTERNS.values())
        except Exception:
            return False

    def parse(self, path: Path, run_id: str) -> RunSummary:
        text = path.read_text(errors="replace")
        summary = RunSummary(run_id=run_id, source="plain_log")

        # Collect all stacktraces for later association
        java_traces = _JAVA_STACKTRACE.findall(text)
        python_traces = _PYTHON_TRACEBACK.findall(text)
        all_traces = java_traces + python_traces

        # Try patterns in order of specificity
        results_found = False

        for fmt, pattern in _PATTERNS.items():
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            results_found = True
            for m in matches:
                result = self._match_to_result(m, fmt, all_traces)
                summary.add(result)
            break  # use the first pattern that matches

        if not results_found:
            # Fall back: try to at least extract failures with stacktraces
            for trace in all_traces:
                first_line = trace.strip().split("\n")[0]
                summary.add(TestResult(
                    name=first_line[:120],
                    classname="unknown",
                    outcome=TestOutcome.FAILED,
                    stacktrace=trace,
                ))

        return summary

    def _match_to_result(
        self, m: re.Match, fmt: str, traces: list[str]
    ) -> TestResult:
        groups = m.groupdict()
        name = groups.get("n", groups.get("name", "unknown"))
        classname = groups.get("class", groups.get("path", ""))
        raw_status = groups.get("status", "").lower()

        outcome = _STATUS_NORM.get(raw_status, None)
        if outcome is None:
            # Try without trailing "ed" — e.g. "passed" → "pass"
            outcome = _STATUS_NORM.get(raw_status.removesuffix("ed"), TestOutcome.FAILED)

        # Try to associate a stacktrace with this failure
        stacktrace = ""
        if outcome in (TestOutcome.FAILED, TestOutcome.ERROR) and traces:
            for trace in traces:
                if name in trace or classname in trace:
                    stacktrace = trace
                    break
            if not stacktrace and traces:
                # Grab the nearest unassigned trace (heuristic)
                stacktrace = traces[0]

        return TestResult(
            name=name,
            classname=classname,
            outcome=outcome,
            stacktrace=stacktrace if stacktrace else None,
        )
