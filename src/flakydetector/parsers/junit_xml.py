"""JUnit XML parser.

Handles the standard JUnit XML format produced by:
- GitHub Actions (via test reporters)
- Gradle/Maven test tasks
- pytest --junitxml
- Most CI systems
- Maven Surefire rerun mode (flakyFailure / rerunFailure elements)
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.parsers import BaseParser


class JUnitXMLParser(BaseParser):
    def can_parse(self, path: Path) -> bool:
        if path.suffix != ".xml":
            return False
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            return root.tag in ("testsuites", "testsuite")
        except ET.ParseError:
            return False

    def parse(self, path: Path, run_id: str) -> RunSummary:
        tree = ET.parse(path)
        root = tree.getroot()
        summary = RunSummary(run_id=run_id, source="junit_xml")

        for suite in self._collect_suites(root):
            suite_name = suite.get("name", "")
            for tc in suite.findall("testcase"):
                result = self._parse_testcase(tc, suite_name)
                summary.add(result)

        return summary

    def _collect_suites(self, root: ET.Element) -> list[ET.Element]:
        """Recursively collect all elements that directly contain <testcase> children.

        Handles: nested <testsuite>, flat <testcase> under <testsuites>, and
        standard single-level <testsuite> structures.
        """
        suites: list[ET.Element] = []

        # If this element directly contains testcases, include it
        if root.findall("testcase"):
            suites.append(root)

        # Recurse into child testsuites
        for child in root:
            if child.tag == "testsuite":
                suites.extend(self._collect_suites(child))

        return suites

    def _parse_testcase(self, tc: ET.Element, suite_name: str) -> TestResult:
        name = tc.get("name", "unknown")
        classname = tc.get("classname", "")
        duration = float(tc.get("time", "0") or "0")

        # Determine outcome — check elements in priority order
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")
        flaky_failure = tc.find("flakyFailure")

        if failure is not None:
            stacktrace = failure.text or ""
            stacktrace = self._append_system_output(tc, stacktrace)
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.FAILED,
                duration_sec=duration,
                error_message=failure.get("message", ""),
                stacktrace=stacktrace,
                suite=suite_name,
            )
        elif error is not None:
            stacktrace = error.text or ""
            stacktrace = self._append_system_output(tc, stacktrace)
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.ERROR,
                duration_sec=duration,
                error_message=error.get("message", ""),
                stacktrace=stacktrace,
                suite=suite_name,
            )
        elif flaky_failure is not None:
            # Maven Surefire: test failed initially but passed on rerun
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.PASSED,
                duration_sec=duration,
                error_message=flaky_failure.get("message", ""),
                stacktrace=flaky_failure.text or "",
                suite=suite_name,
            )
        elif skipped is not None:
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.SKIPPED,
                duration_sec=duration,
                suite=suite_name,
            )
        else:
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.PASSED,
                duration_sec=duration,
                suite=suite_name,
            )

    def _append_system_output(self, tc: ET.Element, stacktrace: str) -> str:
        """Append system-out/system-err to stacktrace for failed/errored tests."""
        sys_out = (tc.findtext("system-out") or "").strip()
        sys_err = (tc.findtext("system-err") or "").strip()
        extra = "\n".join(filter(None, [sys_out, sys_err]))
        if extra:
            return f"{stacktrace}\n{extra}".strip() if stacktrace else extra
        return stacktrace
