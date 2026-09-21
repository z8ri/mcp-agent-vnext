from __future__ import annotations

import time

import pytest

from app.badcases.store import BadCaseStore


@pytest.mark.asyncio
async def test_recorded_case_shows_up_as_unresolved(tmp_path):
    store = BadCaseStore(db_path=str(tmp_path / "bad_cases.sqlite3"))

    case_id = await store.record(
        source="production",
        context="conversation_id=1",
        error_message="something broke",
        error_code="unknown",
        thread_id="thread-1",
        user_id=1,
    )

    unresolved = await store.list_unresolved()
    assert len(unresolved) == 1
    assert unresolved[0].id == case_id
    assert unresolved[0].source == "production"
    assert unresolved[0].error_message == "something broke"
    assert unresolved[0].resolved is False


@pytest.mark.asyncio
async def test_marking_resolved_removes_it_from_unresolved_list(tmp_path):
    store = BadCaseStore(db_path=str(tmp_path / "bad_cases.sqlite3"))
    case_id = await store.record(source="eval", context="some_case", error_message="failed assertion")

    await store.mark_resolved(case_id)

    assert await store.list_unresolved() == []


@pytest.mark.asyncio
async def test_unresolved_list_is_newest_first(tmp_path):
    store = BadCaseStore(db_path=str(tmp_path / "bad_cases.sqlite3"))
    await store.record(source="eval", context="first", error_message="e1")
    await store.record(source="eval", context="second", error_message="e2")

    unresolved = await store.list_unresolved()
    assert [c.context for c in unresolved] == ["second", "first"]


@pytest.mark.asyncio
async def test_purge_resolved_only_deletes_old_resolved_cases(tmp_path):
    import aiosqlite

    db_path = str(tmp_path / "bad_cases.sqlite3")
    store = BadCaseStore(db_path=db_path)

    old_resolved_id = await store.record(source="eval", context="old-resolved", error_message="e1")
    await store.mark_resolved(old_resolved_id)
    recent_resolved_id = await store.record(source="eval", context="recent-resolved", error_message="e2")
    await store.mark_resolved(recent_resolved_id)
    unresolved_id = await store.record(source="eval", context="still-open", error_message="e3")

    # 把"很久以前处理"的那条改到 40 天前，不用真的等 40 天
    old_cutoff = time.time() - 40 * 86400
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("UPDATE bad_cases SET recorded_at = ? WHERE id = ?", (old_cutoff, old_resolved_id))
        await conn.commit()

    deleted = await store.purge_resolved(older_than_days=30)
    assert deleted == 1  # 只删掉超过保留期的那条已处理记录

    # 未处理的记录永远不会被清理，哪怕它也很旧
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("UPDATE bad_cases SET recorded_at = ? WHERE id = ?", (old_cutoff, unresolved_id))
        await conn.commit()
    deleted_again = await store.purge_resolved(older_than_days=30)
    assert deleted_again == 0

    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute("SELECT context FROM bad_cases ORDER BY id")
        remaining = [row[0] for row in await cursor.fetchall()]
    assert remaining == ["recent-resolved", "still-open"]
