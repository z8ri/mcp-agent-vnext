from __future__ import annotations

import pytest
import pytest_asyncio

from app.config import get_settings
from app.db.engine import init_db, make_engine, make_session_factory


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """`get_settings()` 用了 `lru_cache`；不清掉的话，一个测试用 monkeypatch 设的
    环境变量（比如 DATABASE_URL 指到 tmp_path）会被同一个 pytest 进程里更早跑过的
    测试缓存下来的旧 Settings 实例挡住，导致"改了环境变量但设置没变"这种诡异表现。
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = make_session_factory(engine)
    async with factory() as session:
        yield session
