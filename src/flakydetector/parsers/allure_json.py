"""Allure JSON results parser.

Allure generates per-test JSON files in the `allure-results` directory.
Each file is a single test result with status, steps, and attachments.
"""

import json
from pathlib import Path

from flakydetector.models import RunSummary, TestOutcome, TestResult
from flakydetector.parsers import BaseParser

_STATUS_MAP = {
    "passed": TestOutcome.PASSED,
    "failed": TestOutcome.FAILED,
    "broken": TestOutcome.ERROR,
    "skipped": TestOutcome.SKIPPED,
    "pending": TestOutcome.SKIPPED,
}


class AllureJSONParser(BaseParser):
    def can_parse(self, path: Path) -> bool:
        """Works with individual result files or a directory of them."""
        if path.is_dir():
            return any(f.suffix == ".json" for f in path.iterdir())
        if path.suffix != ".json":
            return False
        try:
            data = json.loads(path.read_text())
            return "status" in data and "name" in data
        except (json.JSONDecodeError, KeyError):
            return False

    def parse(self, path: Path, run_id: str) -> RunSummary:
        summary = RunSummary(run_id=run_id, source="allure_json")

        files = sorted(path.glob("*-result.json")) if path.is_dir() else [path]

        # Also try all .json files if the glob above finds nothing
        if path.is_dir() and not files:
            files = sorted(f for f in path.glob("*.json") if f.is_file())

        for f in files:
            try:
                result = self._parse_result_file(f)
                if result:
                    summary.add(result)
            except (json.JSONDecodeError, KeyError):
                continue

        return summary

    def _parse_result_file(self, path: Path) -> TestResult | None:
        data = json.loads(path.read_text())

        status = data.get("status", "unknown")
        if status not in _STATUS_MAP:
            return None

        name = data.get("name", "unknown")
        fullname = data.get("fullName", "")
        classname = fullname.rsplit(".", 1)[0] if "." in fullname else ""

        # Duration: Allure stores start/stop in ms
        start = data.get("start", 0)
        stop = data.get("stop", 0)
        duration_sec = (stop - start) / 1000.0 if stop > start else 0.0

        # Extract failure info
        status_details = data.get("statusDetails", {})
        error_message = status_details.get("message", "")
        stacktrace = status_details.get("trace", "")

        return TestResult(
            name=name,
            classname=classname,
            outcome=_STATUS_MAP[status],
            duration_sec=duration_sec,
            error_message=error_message,
            stacktrace=stacktrace,
            suite=data.get("labels", [{}])[0].get("value", "") if data.get("labels") else "",
            timestamp=str(start) if start else None,
        )
