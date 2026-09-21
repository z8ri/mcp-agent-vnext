"""按 MCP Server 维度的简单熔断器。

熔断只针对单个 server 生效——一个 MCP 连接异常不该把所有 server 的
工具都拖下水，其余 server 的工具应该继续可用。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"        # 正常放行
    OPEN = "open"             # 短路，直接拒绝
    HALF_OPEN = "half_open"   # 冷却时间到，放一个试探请求


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3       # 连续失败几次后打开
    recovery_timeout_s: float = 30.0  # 打开后多久进入半开
    half_open_max_calls: int = 1


class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.config.recovery_timeout_s:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False  # OPEN

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None
        self._half_open_calls = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self.state == CircuitState.HALF_OPEN:
            # 半开探针失败，重新打开并重置冷却计时
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            return
        if self._consecutive_failures >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
        }
