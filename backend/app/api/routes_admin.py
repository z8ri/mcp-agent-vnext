"""健康检查 / 就绪探针：`/healthz` 只答"进程活着"，`/readyz` 逐 MCP server
报告健康状态和熔断器状态，不是笼统的一个布尔值。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["admin"])


@router.get("/healthz")
async def healthz() -> dict:
    """进程本身活着就返回 200，不代表下游 MCP Server 都健康——那是 /readyz 的事。"""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict:
    gateway = request.app.state.gateway
    health_monitor = request.app.state.health_monitor

    await health_monitor.check_all()  # 就绪探针要看当下状态，不能只信上一次周期性检查的缓存

    return {
        "tools_available": gateway.registry.list_available(),
        "rejected_tools": gateway.registry.rejected,
        "circuit_breakers": gateway.breaker_snapshot(),
        "server_health": health_monitor.snapshot(),
    }
