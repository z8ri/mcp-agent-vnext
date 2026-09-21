"""user -> conversation -> LangGraph thread_id，以及同一个 thread 的并发串行化。

`thread_id` 不能是一个客户端可以随便指定的值——那样就不构成用户隔离边界。这里：
- conversation 的归属在数据库里，`get_owned_conversation` 强制校验 user_id；
- 同一个 thread_id 的请求必须拿到同一把 `asyncio.Lock` 才能进 Agent 图，
  避免两个并发请求同时读写同一个 LangGraph checkpoint。

多 worker/多副本场景下 `asyncio.Lock` 只能锁住单进程内的并发，这一点
在 `docs/ENGINEERING_NOTES.md` 里如实写清楚，不夸大成"分布式锁"。
"""

from __future__ import annotations

import asyncio

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import Conversation, User


class ConversationNotFoundError(Exception):
    pass


class ConversationOwnershipError(Exception):
    """conversation 存在，但不属于当前用户——不能因为"不存在"和"越权"用同一个错误码。"""


class SessionManager:
    def __init__(self) -> None:
        self._thread_locks: dict[str, asyncio.Lock] = {}

    def lock_for_thread(self, thread_id: str) -> asyncio.Lock:
        return self._thread_locks.setdefault(thread_id, asyncio.Lock())

    async def create_conversation(self, session: AsyncSession, user: User, title: str = "新对话") -> Conversation:
        conversation = Conversation(user_id=user.id, title=title)
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return conversation

    async def list_conversations(self, session: AsyncSession, user: User) -> list[Conversation]:
        result = await session.exec(
            select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc())
        )
        return list(result.all())

    async def get_owned_conversation(self, session: AsyncSession, user: User, conversation_id: int) -> Conversation:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        if conversation.user_id != user.id:
            raise ConversationOwnershipError(conversation_id)
        return conversation
