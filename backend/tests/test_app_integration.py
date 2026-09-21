"""端到端打通整个 FastAPI 应用：注册/登录 -> 建会话 -> 走 SSE 聊天。

跑的是真实的 `create_app()`（含 lifespan：真实起 weather/write MCP 子进程、
真实建数据库、真实建 Agent 图），只是 `MOCK_MODE=true` 用假模型代替真实 Qwen，
所以不需要任何 API Key。这条测试直接验证了从前端到 MCP Tool Gateway 的
整条链路真的能跑通一个 HTTP 请求。
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _parse_sse(raw_text: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw_text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_line, data_line = block.split("\n", 1)
        event = event_line.removeprefix("event: ")
        data = json.loads(data_line.removeprefix("data: "))
        events.append((event, data))
    return events


@pytest_asyncio.fixture
async def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/app.db")
    monkeypatch.setenv("CHECKPOINT_DB_PATH", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "idempotency.sqlite3"))
    monkeypatch.setenv("TRACE_DB_PATH", str(tmp_path / "trace.sqlite3"))
    monkeypatch.setenv("BUDGET_DB_PATH", str(tmp_path / "budget.sqlite3"))
    monkeypatch.setenv("BAD_CASE_DB_PATH", str(tmp_path / "bad_cases.sqlite3"))
    monkeypatch.setenv("WRITE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("MOCK_MODE", "true")

    from app.main import create_app

    app = create_app()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, tmp_path


@pytest.mark.asyncio
async def test_register_login_and_weather_chat(app_client):
    client, _ = app_client

    register_resp = await client.post(
        "/auth/register", json={"email": "e2e@example.com", "password": "correct horse battery staple"}
    )
    assert register_resp.status_code == 200
    token = register_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    login_resp = await client.post(
        "/auth/login", json={"email": "e2e@example.com", "password": "correct horse battery staple"}
    )
    assert login_resp.status_code == 200

    conv_resp = await client.post("/conversations", json={"title": "天气咨询"}, headers=headers)
    assert conv_resp.status_code == 200
    conversation_id = conv_resp.json()["id"]

    chat_resp = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "今天天气怎么样"}, headers=headers
    )
    assert chat_resp.status_code == 200
    events = _parse_sse(chat_resp.text)
    event_types = [e for e, _ in events]

    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "message" in event_types
    assert event_types[-1] == "final"

    tool_call_event = next(data for e, data in events if e == "tool_call")
    assert tool_call_event["tool"] == "weather.get_weather_tips"


@pytest.mark.asyncio
async def test_write_chat_requires_confirmation_then_writes_file(app_client):
    client, tmp_path = app_client

    await client.post("/auth/register", json={"email": "writer@example.com", "password": "pw123456"})
    login = await client.post("/auth/login", json={"email": "writer@example.com", "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    conv = await client.post("/conversations", json={"title": "写笔记"}, headers=headers)
    conversation_id = conv.json()["id"]

    first = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "帮我写一个笔记"}, headers=headers
    )
    assert first.status_code == 200
    first_events = _parse_sse(first.text)
    assert any(e == "confirm_required" for e, _ in first_events)
    assert not (tmp_path / "workspace").exists() or not list((tmp_path / "workspace").glob("*.txt"))

    second = await client.post(
        "/chat", json={"conversation_id": conversation_id, "confirm": True}, headers=headers
    )
    assert second.status_code == 200
    second_events = _parse_sse(second.text)
    tool_result = next(data for e, data in second_events if e == "tool_result")
    assert tool_result["result"]["ok"] is True

    written_files = list((tmp_path / "workspace").glob("*.txt"))
    assert len(written_files) == 1


@pytest.mark.asyncio
async def test_chat_without_login_is_rejected(app_client):
    client, _ = app_client
    resp = await client.post("/chat", json={"conversation_id": 1, "message": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cannot_chat_on_someone_elses_conversation(app_client):
    client, _ = app_client

    await client.post("/auth/register", json={"email": "owner@example.com", "password": "pw123456"})
    owner_login = await client.post("/auth/login", json={"email": "owner@example.com", "password": "pw123456"})
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    conv = await client.post("/conversations", json={"title": "owner only"}, headers=owner_headers)
    conversation_id = conv.json()["id"]

    await client.post("/auth/register", json={"email": "intruder@example.com", "password": "pw123456"})
    intruder_login = await client.post(
        "/auth/login", json={"email": "intruder@example.com", "password": "pw123456"}
    )
    intruder_headers = {"Authorization": f"Bearer {intruder_login.json()['access_token']}"}

    resp = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "hi"}, headers=intruder_headers
    )
    assert resp.status_code == 404  # 不暴露"这个 ID 属于别人"，统一当不存在处理


@pytest.mark.asyncio
async def test_healthz_and_readyz(app_client):
    client, _ = app_client
    health = await client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    ready = await client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert "weather.get_weather_tips" in body["tools_available"]
    assert body["server_health"]["weather"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_conversation_trace_records_agent_and_tool_spans(app_client):
    client, _ = app_client

    await client.post("/auth/register", json={"email": "trace@example.com", "password": "pw123456"})
    login = await client.post("/auth/login", json={"email": "trace@example.com", "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    conv = await client.post("/conversations", json={"title": "trace demo"}, headers=headers)
    conversation_id = conv.json()["id"]

    await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "今天天气怎么样"}, headers=headers
    )

    trace_resp = await client.get(f"/conversations/{conversation_id}/trace", headers=headers)
    assert trace_resp.status_code == 200
    spans = trace_resp.json()

    span_names = [s["name"] for s in spans]
    assert "agent.invoke" in span_names
    assert "tool.call:weather.get_weather_tips" in span_names
    assert all(s["status"] == "ok" for s in spans)
    assert all(s["duration_ms"] >= 0 for s in spans)

    tool_span = next(s for s in spans if s["name"] == "tool.call:weather.get_weather_tips")
    assert tool_span["attributes"]["ok"] is True


@pytest.mark.asyncio
async def test_trace_endpoint_rejects_other_users_conversation(app_client):
    client, _ = app_client

    await client.post("/auth/register", json={"email": "trace-owner@example.com", "password": "pw123456"})
    owner_login = await client.post(
        "/auth/login", json={"email": "trace-owner@example.com", "password": "pw123456"}
    )
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    conv = await client.post("/conversations", json={"title": "private"}, headers=owner_headers)
    conversation_id = conv.json()["id"]

    await client.post("/auth/register", json={"email": "trace-intruder@example.com", "password": "pw123456"})
    intruder_login = await client.post(
        "/auth/login", json={"email": "trace-intruder@example.com", "password": "pw123456"}
    )
    intruder_headers = {"Authorization": f"Bearer {intruder_login.json()['access_token']}"}

    resp = await client.get(f"/conversations/{conversation_id}/trace", headers=intruder_headers)
    assert resp.status_code == 404
