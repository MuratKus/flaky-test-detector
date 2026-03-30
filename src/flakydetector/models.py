"""Core data models."""

from dataclasses import dataclass, field
from enum import Enum


class TestOutcome(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """A single test execution result."""

    name: str  # fully qualified: com.example.LoginTest.testLogin
    classname: str  # com.example.LoginTest
    outcome: TestOutcome
    duration_sec: float = 0.0
    error_message: str | None = None
    stacktrace: str | None = None
    fingerprint: str | None = None  # set after fingerprinting
    suite: str = ""  # grouping (file, suite name, etc.)
    timestamp: str | None = None
    history_id: str | None = None  # Allure historyId for cross-run identity

    @property
    def fqn(self) -> str:
        """Fully qualified name for deduplication."""
        if self.classname and self.name:
            return f"{self.classname}.{self.name}"
        return self.name


@dataclass
class RunSummary:
    """Summary of a single CI run's parsed results."""

    run_id: str
    source: str  # "junit_xml", "allure_json", "plain_log"
    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    results: list[TestResult] = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        self.total += 1
        match result.outcome:
            case TestOutcome.PASSED:
                self.passed += 1
            case TestOutcome.FAILED:
                self.failed += 1
            case TestOutcome.ERROR:
                self.errored += 1
            case TestOutcome.SKIPPED:
                self.skipped += 1


@dataclass
class TrendPoint:
    """A single data point in a flakiness trend (one run's outcome for a test)."""

    run_id: str
    outcome: str  # "passed", "failed", "error"
    ingested_at: str


@dataclass
class FlakyTest:
    """A test identified as flaky across multiple runs."""

    test_name: str
    total_runs: int
    pass_count: int
    fail_count: int
    flakiness_rate: float  # 0.0 to 1.0 — closer to 0.5 = more flaky
    failure_fingerprints: list[str] = field(default_factory=list)
    last_seen: str | None = None
    recommended_action: str = ""  # "quarantine", "investigate", "stable"
    trend: list[TrendPoint] = field(default_factory=list)
    trend_direction: str = ""  # "improving", "worsening", "stable", ""
    wasted_time_sec: float = 0.0  # total CI time wasted by failed runs
