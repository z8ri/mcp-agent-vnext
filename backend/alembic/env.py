"""Alembic 环境脚本，只管业务数据库（User/Conversation，SQLModel 管理的那部分）。

`app/mcp_gateway/idempotency.py`、`app/trace/tracer.py`、`app/budget/tracker.py`、
`app/badcases/store.py` 各自用裸 `CREATE TABLE IF NOT EXISTS` 管理自己的独立
SQLite 文件——这是有意的范围边界，不是漏做：它们都是单表、只增列不改列的
窄用途日志/缓存表，`CREATE TABLE IF NOT EXISTS` 本身就是够用的"迁移机制"；
把它们也接进 Alembic 反而是过度设计。Alembic 只负责 `database_url` 指向的
那个业务库——`User`/`Conversation` 这类会随需求变化（加字段、加约束、加关联
表）的核心 schema，才是"改字段容易改坏"风险真正集中的地方。
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

from app.config import get_settings
from app.db import models  # noqa: F401 - 让 SQLModel.metadata 收集到 User/Conversation

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable: AsyncEngine = create_async_engine(get_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
