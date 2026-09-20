"""验证 `get_current_user` 依赖链真的能在一个跑起来的 FastAPI 应用里工作。

这里搭的是一个最小化的测试专用 app（不是 Stage E 的正式 app），只是为了在
写正式路由之前，先证明 `request.app.state.session_factory` 这套注入方式、
`OAuth2PasswordBearer` 取 token、`get_current_user` 校验 token 这条链路
本身是通的——避免 Stage E 搭好路由以后才发现依赖注入哪里接不上。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user, get_db_session
from app.auth.security import create_access_token
from app.auth.service import register_user
from app.db.engine import init_db, make_engine, make_session_factory
from app.db.models import User


def _build_app():
    app = FastAPI()

    @app.get("/me")
    async def me(user: User = Depends(get_current_user)):
        return {"email": user.email}

    @app.post("/echo-db")
    async def echo_db(session=Depends(get_db_session)):
        return {"session_type": type(session).__name__}

    return app


@pytest_asyncio.fixture
async def client():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    session_factory = make_session_factory(engine)

    app = _build_app()
    app.state.session_factory = session_factory

    async with session_factory() as session:
        await register_user(session, "dep-test@example.com", "pw")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_valid_token_reaches_protected_route(client):
    token = create_access_token("dep-test@example.com")
    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"email": "dep-test@example.com"}


@pytest.mark.asyncio
async def test_missing_token_is_rejected(client):
    resp = await client.get("/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(client):
    resp = await client.get("/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_for_unknown_user_is_rejected(client):
    token = create_access_token("someone-who-was-never-registered@example.com")
    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
