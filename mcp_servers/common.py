"""三个 MCP Server 共用的最小工具函数。

保持这几个 Server 是可以独立运行的普通脚本（不依赖 backend/app 包）：
Server 只管协议契约和领域执行，不掺进业务框架代码。
"""

from __future__ import annotations

import time
from typing import Any


def ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def err(code: str, message: str, retryable: bool = False) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}


class TTLCache:
    """极简内存 TTL 缓存，避免同一个查询短时间内反复打外部 API。"""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)
