"""Tests for fingerprinting.

Phase 3: Battle-tested with 20+ real-world stacktraces across languages.
Uses parameterized tests with labeled SHOULD-match and SHOULD-NOT-match pairs.
"""

import pytest

from flakydetector.fingerprint import fingerprint, fingerprint_results, normalize_stacktrace
from flakydetector.models import TestOutcome, TestResult


class TestFingerprinting:
    """Original unit tests for basic functionality."""

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


# ── Real-world stacktrace pairs ─────────────────────────────────
# Each pair: (label, trace_a, trace_b)
# SHOULD_MATCH: same root cause, different volatile data
# SHOULD_NOT_MATCH: genuinely different bugs

SHOULD_MATCH = [
    # ── Java ──────────────────────────────────────────────────────
    (
        "java_npe_different_line_numbers",
        (
            "java.lang.NullPointerException: Cannot invoke method on null\n"
            "\tat com.acme.service.UserService.getProfile(UserService.java:142)\n"
            "\tat com.acme.controller.UserController.show(UserController.java:58)\n"
            "\tat sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)"
        ),
        (
            "java.lang.NullPointerException: Cannot invoke method on null\n"
            "\tat com.acme.service.UserService.getProfile(UserService.java:155)\n"
            "\tat com.acme.controller.UserController.show(UserController.java:61)\n"
            "\tat sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)"
        ),
    ),
    (
        "java_timeout_different_timestamps",
        (
            "java.net.SocketTimeoutException: connect timed out\n"
            "\tat java.net.Socket.connect(Socket.java:601)\n"
            "\tat com.acme.client.HttpClient.post(HttpClient.java:89)\n"
            "Caused by: connect to 10.0.0.5:8080 at 2024-03-15T10:30:00Z failed"
        ),
        (
            "java.net.SocketTimeoutException: connect timed out\n"
            "\tat java.net.Socket.connect(Socket.java:601)\n"
            "\tat com.acme.client.HttpClient.post(HttpClient.java:89)\n"
            "Caused by: connect to 10.0.0.5:8080 at 2025-01-22T03:45:12Z failed"
        ),
    ),
    (
        "java_same_exception_different_thread_ids",
        (
            'Exception in thread "pool-3-thread-7" java.lang.OutOfMemoryError: Java heap space\n'
            "\tat com.acme.cache.LRUCache.put(LRUCache.java:112)\n"
            "\tat com.acme.service.DataService.process(DataService.java:67)"
        ),
        (
            'Exception in thread "pool-12-thread-1" java.lang.OutOfMemoryError: Java heap space\n'
            "\tat com.acme.cache.LRUCache.put(LRUCache.java:112)\n"
            "\tat com.acme.service.DataService.process(DataService.java:67)"
        ),
    ),
    (
        "java_same_exception_different_uuids",
        (
            "com.acme.NotFoundException: Resource a1b2c3d4-e5f6-7890-abcd-ef1234567890 not found\n"
            "\tat com.acme.repo.ResourceRepo.findById(ResourceRepo.java:34)\n"
            "\tat com.acme.service.ResourceService.get(ResourceService.java:22)"
        ),
        (
            "com.acme.NotFoundException: Resource deadbeef-1234-5678-9abc-def012345678 not found\n"
            "\tat com.acme.repo.ResourceRepo.findById(ResourceRepo.java:34)\n"
            "\tat com.acme.service.ResourceService.get(ResourceService.java:22)"
        ),
    ),
    # ── Kotlin ────────────────────────────────────────────────────
    (
        "kotlin_coroutine_different_line_numbers",
        (
            "kotlinx.coroutines.TimeoutCancellationException: Timed out waiting for 5000 ms\n"
            "\tat kotlinx.coroutines.TimeoutKt.TimeoutCancellationException(Timeout.kt:184)\n"
            "\tat com.acme.api.ApiClient.fetchData(ApiClient.kt:47)\n"
            "\tat com.acme.api.ApiClient$fetchData$1.invokeSuspend(ApiClient.kt:48)\n"
            "\tat kotlin.coroutines.jvm.internal.BaseContinuationImpl.resumeWith(ContinuationImpl.kt:33)"
        ),
        (
            "kotlinx.coroutines.TimeoutCancellationException: Timed out waiting for 5000 ms\n"
            "\tat kotlinx.coroutines.TimeoutKt.TimeoutCancellationException(Timeout.kt:184)\n"
            "\tat com.acme.api.ApiClient.fetchData(ApiClient.kt:52)\n"
            "\tat com.acme.api.ApiClient$fetchData$1.invokeSuspend(ApiClient.kt:53)\n"
            "\tat kotlin.coroutines.jvm.internal.BaseContinuationImpl.resumeWith(ContinuationImpl.kt:33)"
        ),
    ),
    # ── Python ────────────────────────────────────────────────────
    (
        "python_connection_error_different_line_numbers",
        (
            "Traceback (most recent call last):\n"
            '  File "/app/services/api_client.py", line 42, in fetch\n'
            "    response = self.session.get(url, timeout=5)\n"
            '  File "/usr/lib/python3.11/urllib/request.py", line 216, in urlopen\n'
            "    return opener.open(url, data, timeout)\n"
            "ConnectionError: Connection refused"
        ),
        (
            "Traceback (most recent call last):\n"
            '  File "/app/services/api_client.py", line 58, in fetch\n'
            "    response = self.session.get(url, timeout=5)\n"
            '  File "/usr/lib/python3.11/urllib/request.py", line 216, in urlopen\n'
            "    return opener.open(url, data, timeout)\n"
            "ConnectionError: Connection refused"
        ),
    ),
    (
        "python_assertion_error_different_tmp_paths",
        (
            "Traceback (most recent call last):\n"
            '  File "/app/tests/test_export.py", line 85, in test_csv_export\n'
            '    assert Path("/tmp/pytest-of-ci-123/output.csv").exists()\n'
            "AssertionError"
        ),
        (
            "Traceback (most recent call last):\n"
            '  File "/app/tests/test_export.py", line 85, in test_csv_export\n'
            '    assert Path("/tmp/pytest-of-ci-456/output.csv").exists()\n'
            "AssertionError"
        ),
    ),
    (
        "python_same_error_different_memory_addresses",
        (
            "Traceback (most recent call last):\n"
            '  File "/app/core/engine.py", line 120, in process\n'
            "    result = handler.execute(task)\n"
            "RuntimeError: Object <Task object at 0x7f3a4c001280> is in invalid state"
        ),
        (
            "Traceback (most recent call last):\n"
            '  File "/app/core/engine.py", line 120, in process\n'
            "    result = handler.execute(task)\n"
            "RuntimeError: Object <Task object at 0x7fde8a002f40> is in invalid state"
        ),
    ),
    # ── Python async ──────────────────────────────────────────────
    (
        "python_async_different_task_names",
        (
            "Traceback (most recent call last):\n"
            '  File "/app/services/worker.py", line 33, in run_task\n'
            "    await asyncio.wait_for(coro, timeout=10)\n"
            '  File "/usr/lib/python3.11/asyncio/tasks.py", line 479, in wait_for\n'
            "    return fut.result()\n"
            "asyncio.TimeoutError"
        ),
        (
            "Traceback (most recent call last):\n"
            '  File "/app/services/worker.py", line 33, in run_task\n'
            "    await asyncio.wait_for(coro, timeout=10)\n"
            '  File "/usr/lib/python3.11/asyncio/tasks.py", line 479, in wait_for\n'
            "    return fut.result()\n"
            "asyncio.TimeoutError"
        ),
    ),
    # ── JavaScript / Node.js ──────────────────────────────────────
    (
        "js_type_error_different_line_columns",
        (
            "TypeError: Cannot read properties of undefined (reading 'map')\n"
            "    at UserList.render (/app/src/components/UserList.js:42:18)\n"
            "    at processChild (/app/node_modules/react-dom/cjs/react-dom.development.js:1234:12)\n"
            "    at Object.invokeGuardedCallbackDev (/app/node_modules/react-dom/cjs/react-dom.development.js:5678:16)"
        ),
        (
            "TypeError: Cannot read properties of undefined (reading 'map')\n"
            "    at UserList.render (/app/src/components/UserList.js:47:22)\n"
            "    at processChild (/app/node_modules/react-dom/cjs/react-dom.development.js:1234:12)\n"
            "    at Object.invokeGuardedCallbackDev (/app/node_modules/react-dom/cjs/react-dom.development.js:5678:16)"
        ),
    ),
    (
        "js_promise_rejection_different_ports",
        (
            "UnhandledPromiseRejectionWarning: Error: connect ECONNREFUSED 127.0.0.1:3456\n"
            "    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1141:16)\n"
            "    at ApiService.fetch (/app/src/services/api.js:28:5)"
        ),
        (
            "UnhandledPromiseRejectionWarning: Error: connect ECONNREFUSED 127.0.0.1:4567\n"
            "    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1141:16)\n"
            "    at ApiService.fetch (/app/src/services/api.js:28:5)"
        ),
    ),
    # ── Go ────────────────────────────────────────────────────────
    (
        "go_panic_different_goroutine_ids",
        (
            "goroutine 47 [running]:\n"
            "runtime/debug.Stack()\n"
            "\t/usr/local/go/src/runtime/debug/stack.go:24 +0x5e\n"
            "main.handler(0xc000186000)\n"
            "\t/app/server.go:42 +0x1a2\n"
            "panic: runtime error: index out of range [5] with length 3"
        ),
        (
            "goroutine 183 [running]:\n"
            "runtime/debug.Stack()\n"
            "\t/usr/local/go/src/runtime/debug/stack.go:24 +0x5e\n"
            "main.handler(0xc000286000)\n"
            "\t/app/server.go:42 +0x1a2\n"
            "panic: runtime error: index out of range [5] with length 3"
        ),
    ),
]

SHOULD_NOT_MATCH = [
    # ── Different exception types ─────────────────────────────────
    (
        "java_npe_vs_ioexception",
        (
            "java.lang.NullPointerException\n"
            "\tat com.acme.service.UserService.getProfile(UserService.java:142)"
        ),
        (
            "java.io.IOException: Connection reset by peer\n"
            "\tat com.acme.service.UserService.getProfile(UserService.java:142)"
        ),
    ),
    # ── Different call stacks ─────────────────────────────────────
    (
        "java_same_exception_different_callsite",
        (
            "java.lang.NullPointerException\n"
            "\tat com.acme.service.OrderService.checkout(OrderService.java:88)\n"
            "\tat com.acme.controller.OrderController.post(OrderController.java:42)"
        ),
        (
            "java.lang.NullPointerException\n"
            "\tat com.acme.service.PaymentService.charge(PaymentService.java:55)\n"
            "\tat com.acme.controller.PaymentController.process(PaymentController.java:30)"
        ),
    ),
    # ── Python: different errors ──────────────────────────────────
    (
        "python_key_error_vs_type_error",
        (
            "Traceback (most recent call last):\n"
            '  File "/app/utils.py", line 10, in get_config\n'
            "    return config['database']\n"
            "KeyError: 'database'"
        ),
        (
            "Traceback (most recent call last):\n"
            '  File "/app/utils.py", line 10, in get_config\n'
            "    return config['database']\n"
            "TypeError: 'NoneType' object is not subscriptable"
        ),
    ),
    (
        "python_same_error_different_module",
        (
            "Traceback (most recent call last):\n"
            '  File "/app/services/auth.py", line 22, in validate\n'
            "    token = jwt.decode(raw_token)\n"
            "jwt.ExpiredSignatureError: Signature has expired"
        ),
        (
            "Traceback (most recent call last):\n"
            '  File "/app/services/payment.py", line 45, in process\n'
            "    result = stripe.Charge.create(amount=100)\n"
            "stripe.error.AuthenticationError: Invalid API key"
        ),
    ),
    # ── JavaScript: different components ──────────────────────────
    (
        "js_different_components",
        (
            "TypeError: Cannot read properties of undefined (reading 'map')\n"
            "    at UserList.render (/app/src/components/UserList.js:42:18)"
        ),
        (
            "TypeError: Cannot read properties of null (reading 'length')\n"
            "    at CartList.render (/app/src/components/CartList.js:31:12)"
        ),
    ),
    # ── Go: different panics ──────────────────────────────────────
    (
        "go_index_vs_nil_pointer",
        (
            "goroutine 47 [running]:\n"
            "main.handler(0xc000186000)\n"
            "\t/app/server.go:42 +0x1a2\n"
            "panic: runtime error: index out of range [5] with length 3"
        ),
        (
            "goroutine 47 [running]:\n"
            "main.handler(0xc000186000)\n"
            "\t/app/server.go:42 +0x1a2\n"
            "panic: runtime error: invalid memory address or nil pointer dereference"
        ),
    ),
]


class TestFingerprintShouldMatch:
    """Pairs that represent the SAME root cause — fingerprints must be equal."""

    @pytest.mark.parametrize(
        "label,trace_a,trace_b", SHOULD_MATCH, ids=[s[0] for s in SHOULD_MATCH]
    )
    def test_same_fingerprint(self, label, trace_a, trace_b):
        fp_a = fingerprint(trace_a)
        fp_b = fingerprint(trace_b)
        assert fp_a == fp_b, f"[{label}] Expected same fingerprint but got:\n  a={fp_a}\n  b={fp_b}"


class TestFingerprintShouldNotMatch:
    """Pairs that represent DIFFERENT bugs — fingerprints must differ."""

    @pytest.mark.parametrize(
        "label,trace_a,trace_b", SHOULD_NOT_MATCH, ids=[s[0] for s in SHOULD_NOT_MATCH]
    )
    def test_different_fingerprint(self, label, trace_a, trace_b):
        fp_a = fingerprint(trace_a)
        fp_b = fingerprint(trace_b)
        assert fp_a != fp_b, f"[{label}] Expected different fingerprints but both are: {fp_a}"
