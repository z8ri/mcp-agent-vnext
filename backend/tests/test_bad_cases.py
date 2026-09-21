from __future__ import annotations

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
