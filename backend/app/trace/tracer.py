"""结构化 Trace：每个 Agent 步骤/工具调用落一条 span。

对应档案 §10.4/§11 指出的"无正式 Eval 数据集、trace、任务成功率、延迟……"。
span 用 `thread_id` 串起来，`GET /conversations/{id}/trace` 能按时间顺序拉出
一次对话里"模型想了多久、调了哪个工具、工具花了多久、成功还是失败"，
这是面试时能具体指给别人看的东西，不是只在嘴上说"我们做了可观测性"。

只做进程内够用的粒度：span 之间靠 `parent_span_id` 挂父子关系，暂时没有
跨进程/跨服务的分布式 trace context 传播（MCP transport 那一层目前没有
自己的 span id 可以往下传），这个边界在 VNEXT_STATUS 里写清楚。
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
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_settings().trace_db_path
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
