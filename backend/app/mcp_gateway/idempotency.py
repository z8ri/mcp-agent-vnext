"""写类工具调用的幂等键存储。

对应档案第 12.8 条"验证写文件确认、幂等、并发、防覆盖"：Agent 图在真正调用
一个带副作用的工具之前，先用调用方提供（或按参数派生）的 idempotency_key
查一次；命中就直接回放上次的结果，不重复执行副作用。

用独立的 SQLite 文件，不依赖 Stage D 才建的业务数据库，网关本身可以单独测试。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import aiosqlite

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
    def __init__(self, db_path: str = "./data/idempotency.sqlite3", ttl_seconds: float = 24 * 3600) -> None:
        self._db_path = db_path
        self._ttl = ttl_seconds
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

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
