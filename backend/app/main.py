"""应用组装：把 Gateway、Agent 图、鉴权、SessionManager、限流都接到一起。

对应档案第 11 节候选架构图里从 Vue Client 到 MCP Tool Gateway 的整条链路，
现在是真的能起一个进程、真的能处理 HTTP 请求，不是纸面设计。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.checkpointer import sqlite_checkpointer
from app.agent.graph import build_default_agent_graph
from app.api import routes_admin, routes_auth, routes_chat
from app.badcases.store import BadCaseStore
from app.budget.tracker import BudgetTracker
from app.config import get_settings
from app.db.engine import init_db, make_engine, make_session_factory
from app.mcp_gateway.client import GatewayClient
from app.mcp_gateway.health import HealthMonitor
from app.mcp_gateway.idempotency import IdempotencyStore
from app.mcp_gateway.registry import ServerRegistry
from app.mcp_gateway.server_specs import default_server_specs
from app.security.rate_limit import RateLimiter
from app.security.redaction import configure_logging, get_logger, log_requests_middleware
from app.sessions.manager import SessionManager
from app.trace.tracer import Tracer

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()

    engine = make_engine(settings.database_url)
    await init_db(engine)
    app.state.session_factory = make_session_factory(engine)

    registry = ServerRegistry(default_server_specs())
    await registry.discover_all()
    gateway = GatewayClient(registry, IdempotencyStore(db_path=settings.idempotency_db_path))
    app.state.gateway = gateway

    health_monitor = HealthMonitor(
        server_names=list(registry.specs.keys()), ping=registry.ping, interval_s=60.0
    )
    await health_monitor.check_all()
    await health_monitor.start_background_loop()
    app.state.health_monitor = health_monitor

    app.state.session_manager = SessionManager()
    app.state.rate_limiter = RateLimiter(
        capacity=settings.rate_limit_capacity,
        refill_per_second=settings.rate_limit_refill_per_minute / 60,
    )
    app.state.tracer = Tracer(db_path=settings.trace_db_path)
    app.state.budget_tracker = BudgetTracker(
        db_path=settings.budget_db_path, max_cost_usd_per_user=settings.budget_max_cost_usd_per_user
    )
    app.state.bad_case_store = BadCaseStore(db_path=settings.bad_case_db_path)

    async with sqlite_checkpointer(settings.checkpoint_db_path) as checkpointer:
        app.state.graph = build_default_agent_graph(gateway, checkpointer, tracer=app.state.tracer)
        logger.info(
            "startup_complete",
            mock_mode=settings.mock_mode,
            tools=gateway.registry.list_available(),
            rejected=gateway.registry.rejected,
        )
        yield

    await health_monitor.stop()
    await registry.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MCP Agent vNext", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(log_requests_middleware)

    app.include_router(routes_auth.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_admin.router)

    return app


app = create_app()
