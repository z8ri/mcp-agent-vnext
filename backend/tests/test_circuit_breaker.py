import time

from app.mcp_gateway.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


def test_opens_after_threshold_and_blocks_requests():
    cb = CircuitBreaker("weather", CircuitBreakerConfig(failure_threshold=3, recovery_timeout_s=0.2))

    assert cb.allow_request() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.state.value == "closed"

    cb.record_failure()
    assert cb.state.value == "open"
    assert cb.allow_request() is False


def test_half_open_probe_then_recovers_on_success():
    cb = CircuitBreaker("weather", CircuitBreakerConfig(failure_threshold=1, recovery_timeout_s=0.1))

    cb.record_failure()
    assert cb.state.value == "open"

    time.sleep(0.15)
    assert cb.state.value == "half_open"
    assert cb.allow_request() is True
    assert cb.allow_request() is False  # 半开只放一个探针

    cb.record_success()
    assert cb.state.value == "closed"
    assert cb.allow_request() is True


def test_half_open_probe_failure_reopens():
    cb = CircuitBreaker("write", CircuitBreakerConfig(failure_threshold=1, recovery_timeout_s=0.1))

    cb.record_failure()
    time.sleep(0.15)
    assert cb.state.value == "half_open"

    cb.record_failure()
    assert cb.state.value == "open"
    assert cb.allow_request() is False


def test_each_server_has_independent_breaker_state():
    a = CircuitBreaker("weather", CircuitBreakerConfig(failure_threshold=1))
    b = CircuitBreaker("write", CircuitBreakerConfig(failure_threshold=1))

    a.record_failure()
    assert a.state.value == "open"
    assert b.state.value == "closed"
    assert b.allow_request() is True
