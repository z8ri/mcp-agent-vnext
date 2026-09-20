"""网关调用层：给一次工具调用套上超时 / 重试 / 熔断 / 幂等 / 结构化错误。

Agent 节点（Stage C）不直接摸 `MultiServerMCPClient`，只通过这里的
`GatewayClient.call()`，这样"哪个工具可以自动重试""写操作要不要幂等键"这些
策略都集中在网关，不会散落在 Agent 图的节点代码里。
"""

from __future__ import annotations

import asyncio
import logging

from app.mcp_gateway.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.mcp_gateway.contracts import ErrorCode, ToolError, ToolResult
from app.mcp_gateway.idempotency import IdempotencyStore
from app.mcp_gateway.registry import ServerRegistry

logger = logging.getLogger(__name__)


class GatewayClient:
    def __init__(self, registry: ServerRegistry, idempotency_store: IdempotencyStore | None = None) -> None:
        self.registry = registry
        self.idempotency_store = idempotency_store or IdempotencyStore()
        self._breakers: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(
                name,
                CircuitBreakerConfig(
                    failure_threshold=spec.failure_threshold,
                    recovery_timeout_s=spec.recovery_timeout_s,
                ),
            )
            for name, spec in registry.specs.items()
        }

    def _breaker_for(self, server: str) -> CircuitBreaker:
        return self._breakers.setdefault(server, CircuitBreaker(server))

    async def call(
        self,
        qualified_name: str,
        args: dict,
        *,
        confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        registered = self.registry.get(qualified_name)
        if registered is None:
            return ToolResult.failure(
                server="unknown",
                tool=qualified_name,
                error=ToolError(ErrorCode.NOT_ALLOWED, f"工具 {qualified_name} 不在 Registry 中", retryable=False),
            )

        server, tool_name = registered.server, registered.name
        policy = self.registry.specs[server].policy_for(tool_name)

        if policy.side_effecting and not confirmed:
            return ToolResult.failure(
                server=server,
                tool=tool_name,
                error=ToolError(
                    ErrorCode.CONFIRMATION_REQUIRED,
                    f"{qualified_name} 有副作用，需要先经过 HITL 确认",
                    retryable=False,
                ),
            )

        if policy.side_effecting and idempotency_key:
            cached = await self.idempotency_store.get(idempotency_key)
            if cached is not None:
                return ToolResult(
                    ok=cached["ok"],
                    server=server,
                    tool=tool_name,
                    data=cached.get("data"),
                    error=(
                        ToolError(
                            code=ErrorCode(cached["error"]["code"]),
                            message=cached["error"]["message"],
                            retryable=cached["error"]["retryable"],
                        )
                        if cached.get("error")
                        else None
                    ),
                    idempotent_replay=True,
                )

        breaker = self._breaker_for(server)
        if not breaker.allow_request():
            return ToolResult.failure(
                server=server,
                tool=tool_name,
                error=ToolError(
                    ErrorCode.CIRCUIT_OPEN,
                    f"{server} 熔断中，暂时拒绝调用，其它 server 不受影响",
                    retryable=True,
                ),
            )

        result = await self._invoke_with_policy(registered, args, policy)

        if result.ok:
            breaker.record_success()
        else:
            breaker.record_failure()

        if policy.side_effecting and idempotency_key:
            await self.idempotency_store.put(idempotency_key, server, tool_name, result.to_dict())

        return result

    async def _invoke_with_policy(self, registered, args: dict, policy) -> ToolResult:
        server, tool_name = registered.server, registered.name

        async def _once() -> ToolResult:
            try:
                raw = await asyncio.wait_for(
                    registered.langchain_tool.ainvoke(args), timeout=policy.timeout_s
                )
                return ToolResult.success(server=server, tool=tool_name, data=raw)
            except asyncio.TimeoutError:
                return ToolResult.failure(
                    server=server,
                    tool=tool_name,
                    error=ToolError(ErrorCode.TIMEOUT, f"{tool_name} 调用超过 {policy.timeout_s}s", retryable=True),
                )
            except Exception as exc:  # noqa: BLE001 - 统一转成结构化错误，不把裸异常糊给上层
                logger.warning("工具 %s.%s 调用失败: %s", server, tool_name, exc)
                return ToolResult.failure(
                    server=server,
                    tool=tool_name,
                    error=ToolError(ErrorCode.PROVIDER, str(exc), retryable=policy.retryable),
                )

        if not policy.retryable:
            return await _once()

        max_attempts = 3
        backoff_s = 0.5
        result = await _once()
        attempt = 1
        while (
            not result.ok
            and result.error is not None
            and result.error.retryable
            and attempt < max_attempts
        ):
            await asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 4.0)
            result = await _once()
            attempt += 1
        return result
