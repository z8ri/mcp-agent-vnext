"""写类工具调用的幂等键存储。

Agent 图在真正调用一个带副作用的工具之前，先用调用方提供（或按参数派生）
的 idempotency_key 查一次；命中就直接回放上次的结果，不重复执行副作用。

用独立的 SQLite 文件，不依赖业务数据库，网关本身可以单独测试。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import aiosqlite

from app.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    server TEXT NOT NULL,
    tool TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class IdempotencyStore:
    def __init__(self, db_path: str | None = None, ttl_seconds: float = 24 * 3600) -> None:
        # 默认路径延迟到调用时才读 settings（而不是写死在参数默认值里），
        # 这样测试用 monkeypatch 改 IDEMPOTENCY_DB_PATH 才能真的生效。
        self._db_path = db_path or get_settings().idempotency_db_path
        self._ttl = ttl_seconds
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def get(self, key: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(_SCHEMA)
            cursor = await conn.execute(
                "SELECT result_json, created_at FROM idempotency_keys WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            result_json, created_at = row
            if time.time() - created_at > self._ttl:
                await conn.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
                await conn.commit()
                return None
            return json.loads(result_json)

    async def put(self, key: str, server: str, tool: str, result: dict) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(_SCHEMA)
            await conn.execute(
                """
                INSERT INTO idempotency_keys (key, server, tool, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    result_json = excluded.result_json,
                    created_at = excluded.created_at
                """,
                (key, server, tool, json.dumps(result), time.time()),
            )
            await conn.commit()

    async def purge_expired(self) -> int:
        """主动清掉所有已过 TTL 的行，返回删掉的行数。

        `get()` 里原来的过期判断是懒惰的——只有真的再查一次同一个 key
        才会顺手删掉它；一个 key 如果之后再也没被查过，就会永远留在表里，
        `idempotency_keys` 会跟着请求量单调增长。这个方法用于服务启动时
        主动扫一遍（见 `main.py` 的 lifespan），不依赖"之后有没有人再查它"。
        """
        cutoff = time.time() - self._ttl
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(_SCHEMA)
            cursor = await conn.execute("DELETE FROM idempotency_keys WHERE created_at < ?", (cutoff,))
            await conn.commit()
            return cursor.rowcount
