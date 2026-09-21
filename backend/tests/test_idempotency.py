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


@pytest.mark.asyncio
async def test_purge_expired_deletes_rows_that_were_never_read_again(tmp_path):
    """`get()` 的过期判断是懒惰的——一个 key 如果之后再也没被查过，
    不会自己消失。`purge_expired()` 不依赖"之后有没有人查它"，主动扫一遍。

    `purge_expired()` 的 TTL 来自调用它的这一个 `IdempotencyStore` 实例
    （现实中整个进程只有一个实例，由 settings 统一配置），会用同一个
    截止时间去清表里所有行——不是"每一行按当初写它的那个实例的 TTL 判断"。
    所以这里用同一个 store 实例，靠直接改 `created_at` 来模拟"很久以前写的"，
    而不是像早前那版误用两个不同 TTL 的实例。
    """
    import time

    import aiosqlite

    db_path = str(tmp_path / "idempotency.sqlite3")
    store = IdempotencyStore(db_path=db_path, ttl_seconds=3600)

    await store.put("expired-1", "write", "write_file", {"ok": True, "data": "x"})
    await store.put("expired-2", "write", "write_file", {"ok": True, "data": "y"})
    await store.put("still-fresh", "write", "write_file", {"ok": True, "data": "z"})

    old_cutoff = time.time() - 7200  # 2 小时前，超过 3600s 的 TTL
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE idempotency_keys SET created_at = ? WHERE key IN ('expired-1', 'expired-2')",
            (old_cutoff,),
        )
        await conn.commit()

    deleted = await store.purge_expired()
    assert deleted == 2
    assert await store.get("still-fresh") == {"ok": True, "data": "z"}
