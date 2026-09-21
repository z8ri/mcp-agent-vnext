"""验证日志脱敏真的接进了实际请求日志，不是只在独立脚本里演示过。

`configure_logging()` 用的是 structlog 默认的 `PrintLoggerFactory`，会打到
stdout，所以用 pytest 自带的 `capsys` 直接读控制台输出，不用另外接日志收集器。
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
    monkeypatch.setenv("WRITE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("MOCK_MODE", "true")

    from app.main import create_app

    app = create_app()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_authorization_header_is_redacted_in_request_logs(app_client, capsys):
    client = app_client

    register = await client.post(
        "/auth/register", json={"email": "log-redact@example.com", "password": "pw123456"}
    )
    token = register.json()["access_token"]
    capsys.readouterr()  # 清掉注册请求自己那条日志，只看接下来这一条

    await client.get("/conversations", headers={"Authorization": f"Bearer {token}"})

    captured = capsys.readouterr()
    assert token not in captured.out, "真实 JWT 不应该原样出现在日志里"
    assert "***redacted***" in captured.out
    assert "request_completed" in captured.out
