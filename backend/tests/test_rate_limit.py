"""限流：`TokenBucket` 算法单测 + 真实通过 `/chat` 触发 429 的集成测试。

之前只把 `rate_limited_user` 接成了 `/chat` 的真实依赖，但没有专门测过
"连续请求真的会 429"这条路径——这一条不需要任何外部 Key 或 Docker，
纯粹是之前没有回头补上，这一轮补上。
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.security.rate_limit import RateLimiter, TokenBucket


def test_token_bucket_starts_full_and_denies_when_exhausted():
    bucket = TokenBucket(capacity=3, refill_per_second=0)  # 不自动回充，方便算清楚
    assert bucket.try_consume() is True
    assert bucket.try_consume() is True
    assert bucket.try_consume() is True
    assert bucket.try_consume() is False  # 第 4 次，桶已经空了


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(capacity=1, refill_per_second=20.0)  # 回充很快，方便测试不用等太久
    assert bucket.try_consume() is True
    assert bucket.try_consume() is False  # 立刻再消费一次，桶还是空的

    time.sleep(0.1)  # 0.1s * 20/s = 2 个 token，但封顶在 capacity=1
    assert bucket.try_consume() is True


def test_rate_limiter_buckets_are_independent_per_user():
    limiter = RateLimiter(capacity=1, refill_per_second=0)

    limiter.check(user_id=1)  # 用户 1 的第一次请求，正常通过
    with pytest.raises(HTTPException) as exc_info:
        limiter.check(user_id=1)  # 用户 1 的第二次请求，桶空了，应该被拒绝
    assert exc_info.value.status_code == 429

    limiter.check(user_id=2)  # 用户 2 是完全独立的桶，不受用户 1 影响


@pytest_asyncio.fixture
async def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/app.db")
    monkeypatch.setenv("CHECKPOINT_DB_PATH", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "idempotency.sqlite3"))
    monkeypatch.setenv("TRACE_DB_PATH", str(tmp_path / "trace.sqlite3"))
    monkeypatch.setenv("WRITE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("MOCK_MODE", "true")
    # 容量给到 2，不用真的连发十几次请求才能触发 429。
    monkeypatch.setenv("RATE_LIMIT_CAPACITY", "2")
    monkeypatch.setenv("RATE_LIMIT_REFILL_PER_MINUTE", "0")

    from app.main import create_app

    app = create_app()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_chat_returns_429_after_exceeding_capacity(app_client):
    client = app_client

    register = await client.post(
        "/auth/register", json={"email": "ratelimit@example.com", "password": "pw123456"}
    )
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    conv = await client.post("/conversations", json={"title": "rl"}, headers=headers)
    conversation_id = conv.json()["id"]

    body = {"conversation_id": conversation_id, "message": "你好"}

    first = await client.post("/chat", json=body, headers=headers)
    assert first.status_code == 200

    second = await client.post("/chat", json=body, headers=headers)
    assert second.status_code == 200

    third = await client.post("/chat", json=body, headers=headers)
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_is_per_user(app_client):
    client = app_client

    a = await client.post("/auth/register", json={"email": "rl-a@example.com", "password": "pw123456"})
    a_headers = {"Authorization": f"Bearer {a.json()['access_token']}"}
    a_conv = await client.post("/conversations", json={"title": "a"}, headers=a_headers)
    a_body = {"conversation_id": a_conv.json()["id"], "message": "你好"}

    # 把用户 A 的额度用光
    await client.post("/chat", json=a_body, headers=a_headers)
    await client.post("/chat", json=a_body, headers=a_headers)
    exhausted = await client.post("/chat", json=a_body, headers=a_headers)
    assert exhausted.status_code == 429

    # 用户 B 是完全独立的桶，不应该被用户 A 拖累
    b = await client.post("/auth/register", json={"email": "rl-b@example.com", "password": "pw123456"})
    b_headers = {"Authorization": f"Bearer {b.json()['access_token']}"}
    b_conv = await client.post("/conversations", json={"title": "b"}, headers=b_headers)
    b_body = {"conversation_id": b_conv.json()["id"], "message": "你好"}

    b_first = await client.post("/chat", json=b_body, headers=b_headers)
    assert b_first.status_code == 200
