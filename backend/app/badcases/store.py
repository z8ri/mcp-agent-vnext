"""Bad Case 收集：候选架构横切能力里"Trace / Eval / Bad Case"的最后一项，
早先只做了 Trace 和 Eval，这个漏掉了。

两个来源都写进同一张表：
1. `backend/eval/runner.py` 里失败的场景（脚本化回归，可控、可重现）；
2. 真实 `/chat` 请求里出现的 `error` 事件（生产里的真实失败，不是模拟的）。

这样"回归集"不是一次性写死的几个场景——生产里真的出问题，会自动变成
一条可以查、可以标记"已处理"的记录，而不是打完日志就没人看了。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from app.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bad_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    context TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT NOT NULL,
    thread_id TEXT,
    user_id INTEGER,
    resolved INTEGER NOT NULL DEFAULT 0,
    recorded_at REAL NOT NULL
);
"""


@dataclass
class BadCase:
    id: int
    source: str
    context: str
    error_code: str | None
    error_message: str
    thread_id: str | None
    user_id: int | None
    resolved: bool
    recorded_at: float


class BadCaseStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_settings().bad_case_db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def record(
        self,
        source: str,
        context: str,
        error_message: str,
        *,
        error_code: str | None = None,
        thread_id: str | None = None,
        user_id: int | None = None,
    ) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(_SCHEMA)
            cursor = await conn.execute(
                """
                INSERT INTO bad_cases (source, context, error_code, error_message, thread_id, user_id, resolved, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (source, context, error_code, error_message, thread_id, user_id, time.time()),
            )
            await conn.commit()
            return cursor.lastrowid

    async def list_unresolved(self) -> list[BadCase]:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(_SCHEMA)
            cursor = await conn.execute(
                "SELECT id, source, context, error_code, error_message, thread_id, user_id, resolved, recorded_at "
                "FROM bad_cases WHERE resolved = 0 ORDER BY recorded_at DESC, id DESC"
            )
            rows = await cursor.fetchall()
        return [self._row_to_case(row) for row in rows]

    async def mark_resolved(self, case_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(_SCHEMA)
            await conn.execute("UPDATE bad_cases SET resolved = 1 WHERE id = ?", (case_id,))
            await conn.commit()

    @staticmethod
    def _row_to_case(row: tuple[Any, ...]) -> BadCase:
        case_id, source, context, error_code, error_message, thread_id, user_id, resolved, recorded_at = row
        return BadCase(
            id=case_id,
            source=source,
            context=context,
            error_code=error_code,
            error_message=error_message,
            thread_id=thread_id,
            user_id=user_id,
            resolved=bool(resolved),
            recorded_at=recorded_at,
        )
