import pytest

from app.mcp_gateway.idempotency import IdempotencyStore


@pytest.mark.asyncio
async def test_put_then_get_returns_same_result(tmp_path):
    store = IdempotencyStore(db_path=str(tmp_path / "idempotency.sqlite3"))
    result = {"ok": True, "data": {"path": "note_abc.txt"}}

    assert await store.get("key-1") is None

    await store.put("key-1", server="write", tool="write_file", result=result)
    fetched = await store.get("key-1")

    assert fetched == result


@pytest.mark.asyncio
async def test_different_keys_are_independent(tmp_path):
    store = IdempotencyStore(db_path=str(tmp_path / "idempotency.sqlite3"))

    await store.put("key-a", "write", "write_file", {"ok": True, "data": "a"})
    await store.put("key-b", "write", "write_file", {"ok": True, "data": "b"})

    assert (await store.get("key-a"))["data"] == "a"
    assert (await store.get("key-b"))["data"] == "b"


@pytest.mark.asyncio
async def test_expired_entry_is_treated_as_miss(tmp_path):
    store = IdempotencyStore(db_path=str(tmp_path / "idempotency.sqlite3"), ttl_seconds=0)
    await store.put("key-1", "write", "write_file", {"ok": True, "data": "x"})

    # ttl_seconds=0 意味着写入瞬间就已经过期
    assert await store.get("key-1") is None
