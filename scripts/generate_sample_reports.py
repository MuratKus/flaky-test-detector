#!/usr/bin/env python3
"""Generate sample HTML reports from realistic demo data.

Produces:
  docs/sample-report-run.html     — single run summary (what `flaky-detect report` generates)
  docs/sample-report-flaky.html   — flaky test analysis (what `flaky-detect analyze` generates)
"""

import random
import sys
from pathlib import Path

# Add src to path so we can import without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flakydetector.fingerprint import fingerprint_results
from flakydetector.models import FlakyTest, RunSummary, TestOutcome, TestResult
from flakydetector.reporters.html_report import report_flaky, report_run

DOCS_DIR = Path(__file__).parent.parent / "docs"


def _build_run_summary() -> RunSummary:
    """Build a realistic single-run summary with mixed outcomes."""
    summary = RunSummary(run_id="ci-run-4287", source="junit_xml")

    # Passing tests — realistic service/module names
    passing = [
        ("com.acme.auth.LoginServiceTest", "testLoginWithValidCredentials"),
        ("com.acme.auth.LoginServiceTest", "testLogout"),
        ("com.acme.auth.TokenRefreshTest", "testRefreshExpiredToken"),
        ("com.acme.auth.TokenRefreshTest", "testRefreshWithInvalidToken"),
        ("com.acme.cart.CartServiceTest", "testAddItemToCart"),
        ("com.acme.cart.CartServiceTest", "testRemoveItemFromCart"),
        ("com.acme.cart.CartServiceTest", "testCartTotal"),
        ("com.acme.cart.CheckoutTest", "testCheckoutHappyPath"),
        ("com.acme.cart.CheckoutTest", "testCheckoutEmptyCart"),
        ("com.acme.inventory.StockServiceTest", "testGetStockLevel"),
        ("com.acme.inventory.StockServiceTest", "testReserveStock"),
        ("com.acme.inventory.StockServiceTest", "testReleaseReservation"),
        ("com.acme.notification.EmailServiceTest", "testSendWelcomeEmail"),
        ("com.acme.notification.EmailServiceTest", "testEmailTemplateRendering"),
        ("com.acme.notification.PushNotificationTest", "testSendPush"),
        ("com.acme.search.ProductSearchTest", "testSearchByKeyword"),
        ("com.acme.search.ProductSearchTest", "testSearchWithFilters"),
        ("com.acme.search.ProductSearchTest", "testEmptySearchResults"),
        ("com.acme.payment.PaymentGatewayTest", "testChargeCard"),
        ("com.acme.payment.PaymentGatewayTest", "testRefund"),
        ("com.acme.user.ProfileServiceTest", "testUpdateProfile"),
        ("com.acme.user.ProfileServiceTest", "testDeleteAccount"),
        ("com.acme.user.PreferencesTest", "testSavePreferences"),
    ]
    for cls, name in passing:
        summary.add(TestResult(
            name=name, classname=cls, outcome=TestOutcome.PASSED,
            duration_sec=round(random.uniform(0.05, 2.5), 3),
        ))

    # Skipped tests
    skipped = [
        ("com.acme.payment.PaymentGatewayTest", "testChargeCardWithExpiredCard"),
        ("com.acme.notification.SMSServiceTest", "testSendSMS"),
    ]
    for cls, name in skipped:
        summary.add(TestResult(
            name=name, classname=cls, outcome=TestOutcome.SKIPPED,
        ))

    # Failures — the interesting part
    failures = [
        (
            "com.acme.auth.LoginServiceTest", "testLoginTimeout",
            "Expected response within 5000ms but timed out after 5012ms",
            (
                "java.util.concurrent.TimeoutException: Timeout waiting for response\n"
                "\tat com.acme.auth.HttpClient.send(HttpClient.java:142)\n"
                "\tat com.acme.auth.LoginService.authenticate(LoginService.java:67)\n"
                "\tat com.acme.auth.LoginServiceTest.testLoginTimeout(LoginServiceTest.java:89)\n"
            ),
        ),
        (
            "com.acme.cart.CheckoutTest", "testCheckoutWithPromoCode",
            "AssertionError: expected total 89.99 but got 99.99",
            (
                "java.lang.AssertionError: expected:<89.99> but was:<99.99>\n"
                "\tat org.junit.Assert.assertEquals(Assert.java:115)\n"
                "\tat com.acme.cart.CheckoutTest.testCheckoutWithPromoCode(CheckoutTest.java:134)\n"
            ),
        ),
        (
            "com.acme.inventory.StockServiceTest", "testConcurrentReservation",
            "org.postgresql.util.PSQLException: deadlock detected",
            (
                "org.postgresql.util.PSQLException: ERROR: deadlock detected\n"
                "  Detail: Process 1234 waits for ShareLock on transaction 5678\n"
                "\tat org.postgresql.core.v3.QueryExecutorImpl.receiveErrorResponse(QueryExecutorImpl.java:2553)\n"
                "\tat com.acme.inventory.StockService.reserve(StockService.java:88)\n"
                "\tat com.acme.inventory.StockServiceTest.testConcurrentReservation(StockServiceTest.java:112)\n"
            ),
        ),
    ]
    for cls, name, msg, trace in failures:
        summary.add(TestResult(
            name=name, classname=cls, outcome=TestOutcome.FAILED,
            duration_sec=round(random.uniform(1.0, 8.0), 3),
            error_message=msg, stacktrace=trace,
        ))

    # One error
    summary.add(TestResult(
        name="testWebhookDelivery",
        classname="com.acme.notification.WebhookServiceTest",
        outcome=TestOutcome.ERROR,
        duration_sec=15.2,
        error_message="java.net.ConnectException: Connection refused (localhost:9999)",
        stacktrace=(
            "java.net.ConnectException: Connection refused (Connection refused)\n"
            "\tat java.net.PlainSocketImpl.connect(PlainSocketImpl.java:196)\n"
            "\tat com.acme.notification.WebhookClient.deliver(WebhookClient.java:45)\n"
            "\tat com.acme.notification.WebhookServiceTest.testWebhookDelivery(WebhookServiceTest.java:78)\n"
        ),
    ))

    # Fingerprint all results
    fingerprint_results(summary.results)
    return summary


def _build_flaky_tests() -> list[FlakyTest]:
    """Build a realistic set of flaky test detections."""
    return [
        FlakyTest(
            test_name="com.acme.auth.LoginServiceTest.testLoginTimeout",
            total_runs=12,
            pass_count=6,
            fail_count=6,
            flakiness_rate=1.0,
            failure_fingerprints=["e71ea007e8df4c5a"],
            last_seen="2024-01-15",
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.acme.inventory.StockServiceTest.testConcurrentReservation",
            total_runs=12,
            pass_count=4,
            fail_count=8,
            flakiness_rate=0.67,
            failure_fingerprints=["3b9f1ac2dd6d7812"],
            last_seen="2024-01-15",
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.acme.notification.WebhookServiceTest.testWebhookDelivery",
            total_runs=10,
            pass_count=7,
            fail_count=3,
            flakiness_rate=0.6,
            failure_fingerprints=["a4c10e8833f29b01"],
            last_seen="2024-01-14",
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.acme.search.ProductSearchTest.testSearchWithFilters",
            total_runs=10,
            pass_count=3,
            fail_count=7,
            flakiness_rate=0.6,
            failure_fingerprints=["7d22ff0b4e187a93"],
            last_seen="2024-01-14",
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.acme.cart.CheckoutTest.testCheckoutWithPromoCode",
            total_runs=8,
            pass_count=6,
            fail_count=2,
            flakiness_rate=0.5,
            failure_fingerprints=["c9df22b1a8e04567"],
            last_seen="2024-01-13",
            recommended_action="quarantine",
        ),
        FlakyTest(
            test_name="com.acme.payment.PaymentGatewayTest.testChargeCard",
            total_runs=10,
            pass_count=8,
            fail_count=2,
            flakiness_rate=0.4,
            failure_fingerprints=["f1e2d3c4b5a69780"],
            last_seen="2024-01-12",
            recommended_action="investigate",
        ),
        FlakyTest(
            test_name="com.acme.user.ProfileServiceTest.testUpdateProfile",
            total_runs=10,
            pass_count=8,
            fail_count=2,
            flakiness_rate=0.4,
            failure_fingerprints=["12ab34cd56ef7890"],
            last_seen="2024-01-11",
            recommended_action="investigate",
        ),
        FlakyTest(
            test_name="com.acme.notification.EmailServiceTest.testSendWelcomeEmail",
            total_runs=15,
            pass_count=12,
            fail_count=3,
            flakiness_rate=0.4,
            failure_fingerprints=["88aa99bb00cc11dd"],
            last_seen="2024-01-10",
            recommended_action="investigate",
        ),
    ]


def main():
    random.seed(42)  # reproducible
    DOCS_DIR.mkdir(exist_ok=True)

    # 1) Run summary report
    summary = _build_run_summary()
    run_html = report_run(summary)
    run_path = DOCS_DIR / "sample-report-run.html"
    run_path.write_text(run_html)
    print(f"  Generated {run_path} ({len(run_html):,} bytes)")

    # 2) Flaky analysis report
    flaky_tests = _build_flaky_tests()
    flaky_html = report_flaky(flaky_tests)
    flaky_path = DOCS_DIR / "sample-report-flaky.html"
    flaky_path.write_text(flaky_html)
    print(f"  Generated {flaky_path} ({len(flaky_html):,} bytes)")

    print("\nDone! Open the HTML files in a browser to preview.")


if __name__ == "__main__":
    main()
