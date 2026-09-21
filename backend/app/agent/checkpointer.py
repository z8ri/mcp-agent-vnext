"""SQLite Checkpointer，替换进程内的 `InMemorySaver`。

`InMemorySaver` 只在单进程内有效，进程一重启，所有暂停中的对话状态就没了。
`interrupt()` 做的 HITL 确认暂停依赖 checkpointer 才能跨请求、跨进程重启恢复执行。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def sqlite_checkpointer(db_path: str = "./data/checkpoints.sqlite3") -> AsyncIterator[AsyncSqliteSaver]:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        await saver.setup()
        yield saver
