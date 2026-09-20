"""MCP Server / Tool 的注册表：发现、命名去冲突、allowlist 校验。

依赖 `langchain-mcp-adapters` 的 `MultiServerMCPClient`。不同版本这个包的
"按单个 server 取工具"签名变化过（`get_tools(server_name=...)` 是较新版本
才有的参数），本仓库在没有安装依赖、没有真实环境跑通之前无法把版本锁死验证，
`_get_tools_for_server` 里做了降级处理并在 README 里写明这一点，不假装已验证。
"""

from __future__ import annotations

import inspect
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.mcp_gateway.server_specs import ServerSpec

logger = logging.getLogger(__name__)


class RegisteredTool:
    def __init__(self, server: str, name: str, langchain_tool) -> None:
        self.server = server
        self.name = name                      # 原始工具名（server 内部唯一）
        self.qualified_name = f"{server}.{name}"  # 暴露给 Agent 的去冲突后的名字
        self.langchain_tool = langchain_tool


class ServerRegistry:
    """启动时发现每个 server 的工具，按 allowlist 过滤，按 server 前缀去冲突命名。"""

    def __init__(self, specs: list[ServerSpec]) -> None:
        self.specs = {spec.name: spec for spec in specs}
        self.client = MultiServerMCPClient({spec.name: spec.connection for spec in specs})
        self.tools: dict[str, RegisteredTool] = {}   # qualified_name -> RegisteredTool
        self.rejected: list[dict] = []                # 未通过 allowlist/schema 校验的工具，记录原因

    async def _get_tools_for_server(self, server_name: str) -> list:
        get_tools = self.client.get_tools
        if "server_name" in inspect.signature(get_tools).parameters:
            return await get_tools(server_name=server_name)
        # 旧版本没有按 server 过滤的参数，退化为拿全部工具后按名字前缀猜测归属，
        # 仅用于本地开发容错；生产使用前必须升级到支持 server_name 的版本。
        logger.warning(
            "当前 langchain-mcp-adapters 版本不支持按 server_name 过滤工具，"
            "回退为拉取全部工具后不做 server 校验，请升级依赖后重新验证。"
        )
        return await get_tools()

    async def discover(self, server_name: str) -> None:
        spec = self.specs[server_name]
        try:
            discovered = await self._get_tools_for_server(server_name)
        except Exception as exc:  # noqa: BLE001
            logger.error("MCP server %s 工具发现失败: %s", server_name, exc)
            self.rejected.append({"server": server_name, "reason": f"discovery_failed: {exc}"})
            return

        for tool in discovered:
            name = tool.name
            if name not in spec.allowlist:
                self.rejected.append(
                    {"server": server_name, "tool": name, "reason": "not_in_allowlist"}
                )
                continue
            if not getattr(tool, "description", None):
                self.rejected.append(
                    {"server": server_name, "tool": name, "reason": "missing_description_schema"}
                )
                continue

            registered = RegisteredTool(server=server_name, name=name, langchain_tool=tool)
            if registered.qualified_name in self.tools:
                self.rejected.append(
                    {"server": server_name, "tool": name, "reason": "duplicate_qualified_name"}
                )
                continue
            self.tools[registered.qualified_name] = registered

        # allowlist 里声明了、但 server 实际没暴露的工具，同样要记下来，
        # 不能让"配置说有"被误当成"真的能用"。
        discovered_names = {t.name for t in discovered}
        for expected in spec.allowlist - discovered_names:
            self.rejected.append(
                {"server": server_name, "tool": expected, "reason": "declared_but_not_discovered"}
            )

    async def discover_all(self) -> None:
        for server_name in self.specs:
            await self.discover(server_name)

    def get(self, qualified_name: str) -> RegisteredTool | None:
        return self.tools.get(qualified_name)

    def list_available(self) -> list[str]:
        return sorted(self.tools.keys())

    def bindable_tools(self) -> list:
        """给模型 `bind_tools()` 用的工具列表：把每个工具重命名成 qualified_name。

        模型看到的、tool_calls 里返回的都是 `server.tool` 这个去冲突后的名字，
        Agent 图直接拿它去查网关，不需要再做一次名字映射。
        """
        return [
            registered.langchain_tool.model_copy(update={"name": registered.qualified_name})
            for registered in self.tools.values()
        ]

    async def close(self) -> None:
        cleanup = getattr(self.client, "cleanup", None) or getattr(self.client, "close", None)
        if cleanup is not None:
            await cleanup()
