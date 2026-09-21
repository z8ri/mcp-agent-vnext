"""结构化 Trace：每个 Agent 步骤/工具调用落一条 span。

span 用 `thread_id` 串起来，`GET /conversations/{id}/trace` 能按时间顺序拉出
一次对话里"模型想了多久、调了哪个工具、工具花了多久、成功还是失败"，是可以
实际打开看的数据，不是只停留在"做了可观测性"这句话上。

只做进程内够用的粒度：span 之间靠 `parent_span_id` 挂父子关系，暂时没有
跨进程/跨服务的分布式 trace context 传播（MCP transport 那一层目前没有
自己的 span id 可以往下传），这个边界在 `docs/ENGINEERING_NOTES.md` 里写清楚。
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from app.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_spans (
    span_id TEXT PRIMARY KEY,
    parent_span_id TEXT,
    thread_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at REAL NOT NULL,
    duration_ms REAL NOT NULL,
    attributes_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_spans_thread ON trace_spans (thread_id, started_at);
"""


@dataclass
class SpanRecord:
    span_id: str
    parent_span_id: str | None
    thread_id: str
    name: str
    status: str
    started_at: float
    duration_ms: float
    attributes: dict[str, Any] = field(default_factory=dict)


class Tracer:
    def __init__(self, db_path: str | None = None, retention_days: float | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or settings.trace_db_path
        self._retention_days = retention_days if retention_days is not None else settings.trace_retention_days
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def span(
        self, thread_id: str, name: str, *, parent_span_id: str | None = None, **attributes: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """`attributes` 是可变字典——调用方可以在 `async with` 块内继续往里写，
        比如工具调用结果出来之后再补 `ok`/`error_code`，不用在进 span 之前就知道全部信息。
        """
        span_id = uuid.uuid4().hex
        started_monotonic = time.monotonic()
        started_wall = time.time()
        status = "ok"
        try:
            yield attributes
        except Exception as exc:  # noqa: BLE001 - 记完 span 再往上抛，不吞异常
            status = "error"
            attributes["error"] = str(exc)
            raise
        finally:
            duration_ms = (time.monotonic() - started_monotonic) * 1000
            await self._persist(
                SpanRecord(
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    thread_id=thread_id,
                    name=name,
                    status=status,
                    started_at=started_wall,
                    duration_ms=duration_ms,
                    attributes=attributes,
                )
            )

    async def _persist(self, record: SpanRecord) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(_SCHEMA)
            await conn.execute(
                """
                INSERT INTO trace_spans
                    (span_id, parent_span_id, thread_id, name, status, started_at, duration_ms, attributes_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.span_id,
                    record.parent_span_id,
                    record.thread_id,
                    record.name,
                    record.status,
                    record.started_at,
                    record.duration_ms,
                    json.dumps(record.attributes, ensure_ascii=False, default=str),
                ),
            )
            await conn.commit()

    async def spans_for_thread(self, thread_id: str) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(_SCHEMA)
            cursor = await conn.execute(
                """
                SELECT span_id, parent_span_id, name, status, started_at, duration_ms, attributes_json
                FROM trace_spans WHERE thread_id = ? ORDER BY started_at ASC
                """,
                (thread_id,),
            )
            rows = await cursor.fetchall()

        return [
            {
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "name": name,
                "status": status,
                "started_at": started_at,
                "duration_ms": duration_ms,
                "attributes": json.loads(attributes_json),
            }
            for span_id, parent_span_id, name, status, started_at, duration_ms, attributes_json in rows
        ]

    async def purge_older_than(self, days: float | None = None) -> int:
        """删掉超过保留期的 span，返回删掉的行数。

        每次模型调用、每次工具调用都会落一条 span，长期跑下去
        `trace_spans` 表本身会无限增长，之前完全没有清理机制。这里不引入
        额外的定时任务框架——`main.py` 的 lifespan 在每次进程启动时调一次，
        对这个项目的规模够用；真要 7x24 常驻部署，应该换成独立的定时任务。
        """
        retention_days = self._retention_days if days is None else days
        cutoff = time.time() - retention_days * 86400
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(_SCHEMA)
            cursor = await conn.execute("DELETE FROM trace_spans WHERE started_at < ?", (cutoff,))
            await conn.commit()
            return cursor.rowcount
