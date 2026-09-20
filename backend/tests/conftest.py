from __future__ import annotations

import pytest_asyncio

from app.db.engine import init_db, make_engine, make_session_factory


@pytest_asyncio.fixture
async def db_session():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = make_session_factory(engine)
    async with factory() as session:
        yield session
