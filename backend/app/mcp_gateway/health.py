"""每个 MCP Server 的独立健康状态。

对应档案 §10.2："任一 MCP 连接异常会被整体捕获并令工具列表变成空列表，
没有 per-server readiness、局部降级和明确健康状态"。这里维护每个 server
独立的 healthy/unhealthy 状态，一个挂了不影响其它 server 的工具继续可用。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class ServerHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthRecord:
    status: ServerHealth = ServerHealth.UNKNOWN
    last_checked_at: float | None = None
    last_error: str | None = None


PingFn = Callable[[str], Awaitable[None]]  # 抛异常代表不健康，正常返回代表健康


class HealthMonitor:
    def __init__(self, server_names: list[str], ping: PingFn, interval_s: float = 30.0) -> None:
        self._server_names = server_names
        self._ping = ping
        self._interval_s = interval_s
        self._records: dict[str, HealthRecord] = {name: HealthRecord() for name in server_names}
        self._task: asyncio.Task | None = None

    async def check_once(self, server_name: str) -> HealthRecord:
        record = self._records.setdefault(server_name, HealthRecord())
        try:
            await self._ping(server_name)
            record.status = ServerHealth.HEALTHY
            record.last_error = None
        except Exception as exc:  # noqa: BLE001 - 健康检查本身要吞掉任何异常
            record.status = ServerHealth.UNHEALTHY
            record.last_error = str(exc)
            logger.warning("MCP server %s 健康检查失败: %s", server_name, exc)
        record.last_checked_at = time.time()
        return record

    async def check_all(self) -> dict[str, HealthRecord]:
        await asyncio.gather(*(self.check_once(name) for name in self._server_names))
        return self._records

    def snapshot(self) -> dict[str, dict]:
        return {
            name: {
                "status": record.status.value,
                "last_checked_at": record.last_checked_at,
                "last_error": record.last_error,
            }
            for name, record in self._records.items()
        }

    def is_ready(self, server_name: str) -> bool:
        record = self._records.get(server_name)
        return record is not None and record.status == ServerHealth.HEALTHY

    async def start_background_loop(self) -> None:
        if self._task is not None:
            return

        async def _loop() -> None:
            while True:
                await self.check_all()
                await asyncio.sleep(self._interval_s)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
