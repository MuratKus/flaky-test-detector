"""JUnit XML parser.

Handles the standard JUnit XML format produced by:
- GitHub Actions (via test reporters)
- Gradle/Maven test tasks
- pytest --junitxml
- Most CI systems
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.parsers import BaseParser


class JUnitXMLParser(BaseParser):

    def can_parse(self, path: Path) -> bool:
        if not path.suffix == ".xml":
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

        suites = (
            root.findall("testsuite")
            if root.tag == "testsuites"
            else [root]
        )

        for suite in suites:
            suite_name = suite.get("name", "")
            for tc in suite.findall("testcase"):
                result = self._parse_testcase(tc, suite_name)
                summary.add(result)

        return summary

    def _parse_testcase(self, tc: ET.Element, suite_name: str) -> TestResult:
        name = tc.get("name", "unknown")
        classname = tc.get("classname", "")
        duration = float(tc.get("time", "0") or "0")

        # Determine outcome
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.FAILED,
                duration_sec=duration,
                error_message=failure.get("message", ""),
                stacktrace=failure.text or "",
                suite=suite_name,
            )
        elif error is not None:
            return TestResult(
                name=name,
                classname=classname,
                outcome=TestOutcome.ERROR,
                duration_sec=duration,
                error_message=error.get("message", ""),
                stacktrace=error.text or "",
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
