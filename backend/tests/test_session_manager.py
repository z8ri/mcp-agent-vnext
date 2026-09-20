from __future__ import annotations

import asyncio

import pytest

from app.auth.service import register_user
from app.sessions.manager import (
    ConversationNotFoundError,
    ConversationOwnershipError,
    SessionManager,
)


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_conversation(db_session):
    alice = await register_user(db_session, "alice@example.com", "pw")
    bob = await register_user(db_session, "bob@example.com", "pw")

    manager = SessionManager()
    alice_conv = await manager.create_conversation(db_session, alice, title="alice's notes")

    # alice 自己能拿到
    fetched = await manager.get_owned_conversation(db_session, alice, alice_conv.id)
    assert fetched.id == alice_conv.id

    # bob 想访问 alice 的 conversation 应该被拒绝，而不是意外拿到
    with pytest.raises(ConversationOwnershipError):
        await manager.get_owned_conversation(db_session, bob, alice_conv.id)


@pytest.mark.asyncio
async def test_nonexistent_conversation_raises_not_found(db_session):
    alice = await register_user(db_session, "alice2@example.com", "pw")
    manager = SessionManager()

    with pytest.raises(ConversationNotFoundError):
        await manager.get_owned_conversation(db_session, alice, 9999)


@pytest.mark.asyncio
async def test_list_conversations_only_returns_own(db_session):
    alice = await register_user(db_session, "alice3@example.com", "pw")
    bob = await register_user(db_session, "bob3@example.com", "pw")
    manager = SessionManager()

    await manager.create_conversation(db_session, alice, title="a1")
    await manager.create_conversation(db_session, alice, title="a2")
    await manager.create_conversation(db_session, bob, title="b1")

    alice_list = await manager.list_conversations(db_session, alice)
    assert {c.title for c in alice_list} == {"a1", "a2"}


@pytest.mark.asyncio
async def test_same_thread_lock_serializes_concurrent_access():
    manager = SessionManager()
    order: list[str] = []

    async def worker(name: str, hold_seconds: float):
        async with manager.lock_for_thread("thread-x"):
            order.append(f"{name}-start")
            await asyncio.sleep(hold_seconds)
            order.append(f"{name}-end")

    await asyncio.gather(worker("first", 0.05), worker("second", 0.01))

    # 如果锁没生效，"second" 会在 "first" 结束前插进来；有锁的话必须严格是
    # first-start, first-end, second-start, second-end 这个顺序。
    assert order == ["first-start", "first-end", "second-start", "second-end"]


@pytest.mark.asyncio
async def test_different_threads_do_not_block_each_other():
    manager = SessionManager()
    order: list[str] = []

    async def worker(name: str, thread_id: str, hold_seconds: float):
        async with manager.lock_for_thread(thread_id):
            order.append(f"{name}-start")
            await asyncio.sleep(hold_seconds)
            order.append(f"{name}-end")

    await asyncio.gather(worker("a", "thread-a", 0.05), worker("b", "thread-b", 0.01))

    # 不同 thread 的锁互相独立，"b" 应该能在 "a" 还没结束时就跑完。
    assert order.index("b-end") < order.index("a-end")
