"""业务数据库表：用户、会话（conversation）。

消息内容本身不重复存一份——LangGraph 的 SqliteSaver（`app/agent/checkpointer.py`）
已经按 thread_id 存了完整的消息状态，这里的 `Conversation` 只是
"user 拥有哪些 conversation、每个 conversation 对应哪个 thread_id" 的归属表，
避免同一份数据有两个来源、两边容易写歪。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=_now)


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex, index=True, unique=True)
    title: str = "新对话"
    created_at: datetime = Field(default_factory=_now)
