"""Unit tests for the AI investigator."""
from flakydetector.models import InvestigationResult


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
