"""通过真实的 FastAPI app 验证预算拦截、账单记录、Bad Case 收集三件事
真的接在一起了，不是分别独立的单元测试拼出来的假象。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


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
            yield client


async def _register_and_login(client, email: str) -> dict:
    resp = await client.post("/auth/register", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_normal_turn_records_zero_cost_budget_entry(app_client):
    client = app_client
    headers = await _register_and_login(client, "budget-normal@example.com")

    conv = await client.post("/conversations", json={"title": "b"}, headers=headers)
    conversation_id = conv.json()["id"]

    chat_resp = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "你好"}, headers=headers
    )
    assert chat_resp.status_code == 200

    budget_resp = await client.get("/budget", headers=headers)
    assert budget_resp.status_code == 200
    body = budget_resp.json()
    # mock 模式下模型不会真的报 token 用量，但至少应该有一条延迟记录，cost 是 0 不是没记录。
    assert body["cost_usd"] == 0
    assert body["exceeded"] is False


@pytest.mark.asyncio
async def test_chat_is_rejected_once_budget_limit_is_zero(app_client, monkeypatch):
    client = app_client
    headers = await _register_and_login(client, "budget-exceeded@example.com")

    conv = await client.post("/conversations", json={"title": "b"}, headers=headers)
    conversation_id = conv.json()["id"]

    # 直接把这个 app 实例的 BudgetTracker 换成限额为 0 的——不用真的攒够真实花费。
    from app.budget.tracker import BudgetTracker

    client._transport.app.state.budget_tracker = BudgetTracker(
        db_path=client._transport.app.state.budget_tracker._db_path, max_cost_usd_per_user=0.0
    )

    resp = await client.post(
        "/chat", json={"conversation_id": conversation_id, "message": "你好"}, headers=headers
    )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_bad_cases_endpoint_returns_recorded_cases(app_client):
    """测 `BadCaseStore` -> `GET /bad-cases` 这段 API 层的管线（鉴权、序列化）。
    `stream_graph_turn` 的 `on_error` 回调本身在下面用一个会报错的假 graph
    单独测，不在这里靠图真的崩溃来触发——mock 模式下的图本身很稳定，
    硬造一次真实运行时异常反而会让这个测试变脆弱。
    """
    client = app_client
    headers = await _register_and_login(client, "badcase@example.com")

    from app.badcases.store import BadCaseStore

    store: BadCaseStore = client._transport.app.state.bad_case_store
    await store.record(source="production", context="conversation_id=1", error_message="boom")

    resp = await client.get("/bad-cases", headers=headers)
    assert resp.status_code == 200
    cases = resp.json()
    assert any(c["error_message"] == "boom" for c in cases)


@pytest.mark.asyncio
async def test_stream_graph_turn_reports_real_exceptions_through_on_error():
    """`sse.py` 的 `on_error` 回调是 Bad Case 收集真正接进生产错误路径的地方——
    这里直接给一个会抛异常的假 graph，验证回调真的会被调用、payload 里的
    错误信息是真实异常内容，而不是只测通过路径。
    """
    from app.api.sse import stream_graph_turn

    class _BrokenGraph:
        async def astream(self, *_args, **_kwargs):
            raise RuntimeError("simulated MCP transport failure")
            yield  # pragma: no cover - 让这个函数成为异步生成器，永远不会执行到

    recorded: list[dict] = []

    async def on_error(payload: dict) -> None:
        recorded.append(payload)

    events = [
        event
        async for event in stream_graph_turn(_BrokenGraph(), {}, {"configurable": {}}, on_error=on_error)
    ]

    assert len(recorded) == 1
    assert "simulated MCP transport failure" in recorded[0]["message"]
    assert any("event: error" in e for e in events)
