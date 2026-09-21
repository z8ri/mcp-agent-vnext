"""`Tracer.purge_older_than()`：trace_spans 表没有清理策略会无限增长，
这里直接测"旧的真的被删了、新的真的留下来了"，不只是代码走查。
"""

from __future__ import annotations

import time

import pytest

from app.trace.tracer import Tracer


@pytest.mark.asyncio
async def test_purge_older_than_removes_only_stale_spans(tmp_path):
    tracer = Tracer(db_path=str(tmp_path / "trace.sqlite3"), retention_days=30)

    async with tracer.span("thread-old", "agent.invoke"):
        pass
    async with tracer.span("thread-new", "agent.invoke"):
        pass

    # 直接改数据库里那条旧 span 的 started_at，模拟"很久以前写的"，
    # 不用真的等 30 天。
    import aiosqlite

    old_cutoff = time.time() - 40 * 86400
    async with aiosqlite.connect(str(tmp_path / "trace.sqlite3")) as conn:
        await conn.execute(
            "UPDATE trace_spans SET started_at = ? WHERE thread_id = 'thread-old'", (old_cutoff,)
        )
        await conn.commit()

    deleted = await tracer.purge_older_than()
    assert deleted == 1

    remaining_old = await tracer.spans_for_thread("thread-old")
    remaining_new = await tracer.spans_for_thread("thread-new")
    assert remaining_old == []
    assert len(remaining_new) == 1


@pytest.mark.asyncio
async def test_purge_older_than_accepts_explicit_days_override(tmp_path):
    tracer = Tracer(db_path=str(tmp_path / "trace.sqlite3"), retention_days=30)

    async with tracer.span("thread-a", "agent.invoke"):
        pass

    # 显式传 days=0：现在写的 span 相对"0 天前"也算过期，直接验证参数确实生效
    deleted = await tracer.purge_older_than(days=0)
    assert deleted == 1
    assert await tracer.spans_for_thread("thread-a") == []
