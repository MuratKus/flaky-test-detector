"""Plain text log parser.

Extracts test results from raw CI stdout/stderr logs using common patterns:
- Gradle test output (including parameterized tests)
- pytest output (one-liner and === FAILURES === blocks)
- Maven Surefire output
- Generic PASSED/FAILED markers
- Java/Python stacktrace extraction
"""

import re
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.parsers import BaseParser

# ANSI escape sequence stripper
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Patterns for different test frameworks
_PATTERNS = {
    # Gradle: "com.example.MyTest > testLogin FAILED" or "... > testLogin[Chrome] FAILED"
    "gradle": re.compile(
        r"^(?P<class>[\w.]+)\s*>\s*(?P<name>\w+(?:\[.*?\])?)(?:\(.*?\))?\s+"
        r"(?P<status>PASSED|FAILED|SKIPPED)",
        re.MULTILINE,
    ),
    # pytest: "tests/test_foo.py::test_bar PASSED" or "...::test_bar[param] PASSED"
    "pytest": re.compile(
        r"^(?P<path>[\w/._-]+)::(?P<name>[\w\[\]\-.,]+)\s+"
        r"(?P<status>PASSED|FAILED|ERROR|SKIPPED)",
        re.MULTILINE,
    ),
    # Generic: "TEST testName ... PASSED"
    "generic": re.compile(
        r"(?:TEST|test)\s+(?P<name>[\w.]+)\s*\.{0,3}\s*"
        r"(?P<status>PASS(?:ED)?|FAIL(?:ED)?|SKIP(?:PED)?|ERROR)",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Maven Surefire patterns
_MAVEN_HEADER = re.compile(r"T E S T S")
_MAVEN_RUNNING = re.compile(r"^Running\s+(?P<class>[\w.]+)", re.MULTILINE)
_MAVEN_CLASS_SUMMARY = re.compile(
    r"^Tests run:\s*(?P<total>\d+),\s*Failures:\s*(?P<failures>\d+),\s*"
    r"Errors:\s*(?P<errors>\d+),\s*Skipped:\s*(?P<skipped>\d+).*?(?:in\s+(?P<class>[\w.]+))?$",
    re.MULTILINE,
)
_MAVEN_FAILURE = re.compile(
    r"^(?P<name>\w+)\((?P<class>[\w.]+)\)\s+Time elapsed:.*?<<<\s*(?P<status>FAILURE|ERROR)!",
    re.MULTILINE,
)

# Pytest failure block patterns
_PYTEST_FAILURE_HEADER = re.compile(r"^=+ FAILURES =+$", re.MULTILINE)
_PYTEST_FAILURE_DIVIDER = re.compile(r"^_+ ([\w\[\]\-.,]+) _+$", re.MULTILINE)
_PYTEST_SHORT_SUMMARY = re.compile(
    r"^FAILED\s+(?P<path>[\w/._-]+)::(?P<name>[\w\[\]\-.,]+)\s*-\s*(?P<msg>.+)$",
    re.MULTILINE,
)

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
    "failure": TestOutcome.FAILED,
    "error": TestOutcome.ERROR,
    "skipped": TestOutcome.SKIPPED,
    "skip": TestOutcome.SKIPPED,
}


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


class PlainLogParser(BaseParser):
    def can_parse(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.suffix in (".xml", ".json"):
            return False
        try:
            text = _strip_ansi(path.read_text(errors="replace")[:8000])
            # Check for Maven Surefire
            if _MAVEN_HEADER.search(text):
                return True
            return any(p.search(text) for p in _PATTERNS.values())
        except Exception:
            return False

    def parse(self, path: Path, run_id: str) -> RunSummary:
        text = _strip_ansi(path.read_text(errors="replace"))
        summary = RunSummary(run_id=run_id, source="plain_log")

        # Collect all stacktraces with positions for association
        java_traces = [(m.start(), m.group()) for m in _JAVA_STACKTRACE.finditer(text)]
        python_traces = [(m.start(), m.group()) for m in _PYTHON_TRACEBACK.finditer(text)]
        all_traces = java_traces + python_traces
        all_traces.sort(key=lambda t: t[0])

        # Try specialized parsers first (most reliable)
        if _MAVEN_HEADER.search(text):
            return self._parse_maven_surefire(text, summary, all_traces)

        if _PYTEST_FAILURE_HEADER.search(text):
            return self._parse_pytest_verbose(text, summary, all_traces)

        # Fall back to pattern-based matching
        return self._parse_with_patterns(text, summary, all_traces)

    def _parse_with_patterns(
        self,
        text: str,
        summary: RunSummary,
        traces: list[tuple[int, str]],
    ) -> RunSummary:
        """Match test results using regex patterns."""
        claimed: set[int] = set()

        for pattern in _PATTERNS.values():
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            for m in matches:
                result = self._match_to_result(m, traces, claimed)
                summary.add(result)
            return summary  # use first matching pattern

        # Fall back: extract failures from stacktraces alone
        for _pos, trace in traces:
            first_line = trace.strip().split("\n")[0]
            summary.add(
                TestResult(
                    name=first_line[:120],
                    classname="unknown",
                    outcome=TestOutcome.FAILED,
                    stacktrace=trace,
                )
            )
        return summary

    def _parse_pytest_verbose(
        self,
        text: str,
        summary: RunSummary,
        traces: list[tuple[int, str]],
    ) -> RunSummary:
        """Parse pytest output with === FAILURES === section."""
        # 1. Parse one-liner results for all tests
        one_liner_matches = list(_PATTERNS["pytest"].finditer(text))

        # Build a map from test name to short summary info
        short_summary: dict[str, tuple[str, str]] = {}  # name -> (path, msg)
        for m in _PYTEST_SHORT_SUMMARY.finditer(text):
            short_summary[m.group("name")] = (m.group("path"), m.group("msg"))

        # Extract failure blocks between dividers
        failure_header = _PYTEST_FAILURE_HEADER.search(text)
        failure_traces: dict[str, str] = {}  # test_name -> stacktrace block
        if failure_header:
            failure_section = text[failure_header.end() :]
            # Find where the failure section ends (next === line)
            end_match = re.search(r"^=+\s+\S", failure_section, re.MULTILINE)
            if end_match:
                failure_section = failure_section[: end_match.start()]

            # Split by dividers
            dividers = list(_PYTEST_FAILURE_DIVIDER.finditer(failure_section))
            for i, div in enumerate(dividers):
                test_name = div.group(1)
                start = div.end()
                end = dividers[i + 1].start() if i + 1 < len(dividers) else len(failure_section)
                block = failure_section[start:end].strip()
                failure_traces[test_name] = block

        # 2. Process one-liner results
        seen_names: set[str] = set()
        for m in one_liner_matches:
            groups = m.groupdict()
            name = groups.get("name", "unknown")
            classname = groups.get("path", "")
            raw_status = groups.get("status", "").lower()
            outcome = _STATUS_NORM.get(raw_status, TestOutcome.FAILED)

            # Attach stacktrace from failure blocks if available
            stacktrace = failure_traces.get(name)

            seen_names.add(name)
            summary.add(
                TestResult(
                    name=name,
                    classname=classname,
                    outcome=outcome,
                    stacktrace=stacktrace,
                )
            )

        # 3. Add any failures from short summary that weren't in one-liners
        for name, (path, msg) in short_summary.items():
            if name not in seen_names:
                summary.add(
                    TestResult(
                        name=name,
                        classname=path,
                        outcome=TestOutcome.FAILED,
                        error_message=msg,
                        stacktrace=failure_traces.get(name),
                    )
                )

        return summary

    def _parse_maven_surefire(
        self,
        text: str,
        summary: RunSummary,
        traces: list[tuple[int, str]],
    ) -> RunSummary:
        """Parse Maven Surefire output."""
        # Parse individual failure lines
        failures: dict[str, str] = {}  # (name) -> classname
        claimed: set[int] = set()

        for m in _MAVEN_FAILURE.finditer(text):
            name = m.group("name")
            classname = m.group("class")
            failures[name] = classname

            # Find nearest stacktrace after this failure line
            stacktrace = self._find_nearest_trace(m.end(), traces, claimed)

            outcome = TestOutcome.ERROR if m.group("status") == "ERROR" else TestOutcome.FAILED
            summary.add(
                TestResult(
                    name=name,
                    classname=classname,
                    outcome=outcome,
                    stacktrace=stacktrace,
                )
            )

        # Parse the final summary line (last "Tests run:" not followed by "in <class>")
        # to get total counts and infer passed tests
        summary_matches = list(_MAVEN_CLASS_SUMMARY.finditer(text))
        if summary_matches:
            # Use the last summary (the aggregate one)
            final = summary_matches[-1]
            total = int(final.group("total"))
            fail_count = int(final.group("failures"))
            error_count = int(final.group("errors"))
            skip_count = int(final.group("skipped"))
            pass_count = total - fail_count - error_count - skip_count

            # Add skipped entries
            for i in range(skip_count):
                summary.add(
                    TestResult(
                        name=f"skipped_{i + 1}",
                        classname="",
                        outcome=TestOutcome.SKIPPED,
                    )
                )

            # Add inferred passing tests
            for i in range(pass_count):
                summary.add(
                    TestResult(
                        name=f"passed_{i + 1}",
                        classname="",
                        outcome=TestOutcome.PASSED,
                    )
                )

        return summary

    def _match_to_result(
        self,
        m: re.Match,
        traces: list[tuple[int, str]],
        claimed: set[int],
    ) -> TestResult:
        groups = m.groupdict()
        name = groups.get("n", groups.get("name", "unknown"))
        classname = groups.get("class", groups.get("path", ""))
        raw_status = groups.get("status", "").lower()

        outcome = _STATUS_NORM.get(raw_status)
        if outcome is None:
            outcome = _STATUS_NORM.get(raw_status.removesuffix("ed"), TestOutcome.FAILED)

        # Associate stacktrace with failures
        stacktrace: str | None = None
        if outcome in (TestOutcome.FAILED, TestOutcome.ERROR) and traces:
            stacktrace = self._find_nearest_trace(m.end(), traces, claimed, name, classname)

        return TestResult(
            name=name,
            classname=classname,
            outcome=outcome,
            stacktrace=stacktrace if stacktrace else None,
        )

    @staticmethod
    def _find_nearest_trace(
        after_pos: int,
        traces: list[tuple[int, str]],
        claimed: set[int],
        name: str = "",
        classname: str = "",
    ) -> str | None:
        """Find the nearest unclaimed stacktrace, preferring name/class match."""
        # First try name/class match
        for i, (_pos, trace) in enumerate(traces):
            if i in claimed:
                continue
            if (name and name in trace) or (classname and classname in trace):
                claimed.add(i)
                return trace

        # Fall back to nearest trace after the match position
        for i, (pos, trace) in enumerate(traces):
            if i in claimed:
                continue
            if pos > after_pos:
                claimed.add(i)
                return trace

        return None
