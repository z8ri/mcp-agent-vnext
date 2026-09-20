"""MCP Server 的声明式配置：连接方式 + 网关侧元数据。

机构参考代码的 `servers_config.json` 只描述怎么连接（command/url），
不知道哪个工具有副作用、要不要重试、超时多久。这里把两件事合在一起，
Registry 用它来发现+校验工具，GatewayClient 用它来决定重试/熔断/幂等策略。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings

MCP_SERVERS_DIR = Path(__file__).resolve().parents[3] / "mcp_servers"


def _forward_env(*names: str) -> dict[str, str]:
    """MCP stdio transport 默认只给子进程一份精简环境（`get_default_environment()`），
    不会整包转发父进程的 `os.environ`——这是好事（不会把无关密钥泄露给本地子进程），
    但意味着子进程需要的变量必须显式在这里列出来转发，不能指望"反正是同一台机器"。
    """
    return {name: os.environ[name] for name in names if name in os.environ}


@dataclass
class ToolPolicy:
    side_effecting: bool = False   # 有副作用（比如写文件），需要 HITL 确认 + 幂等键
    retryable: bool = False        # 网关是否可以在失败时自动重试（只对安全、幂等的读操作开）
    timeout_s: float = 15.0


@dataclass
class ServerSpec:
    name: str
    connection: dict                       # 直接喂给 MultiServerMCPClient 的连接描述
    allowlist: set[str]                     # 允许暴露给 Agent 的工具名（未在此的一律拒绝）
    tool_policies: dict[str, ToolPolicy] = field(default_factory=dict)
    max_retries: int = 2
    failure_threshold: int = 3
    recovery_timeout_s: float = 30.0

    def policy_for(self, tool_name: str) -> ToolPolicy:
        return self.tool_policies.get(tool_name, ToolPolicy())


def default_server_specs() -> list[ServerSpec]:
    settings = get_settings()
    python = sys.executable

    weather = ServerSpec(
        name="weather",
        connection={
            "command": python,
            "args": [str(MCP_SERVERS_DIR / "weather_server.py")],
            "transport": "stdio",
            # weather_server.py 自己也会 load_dotenv()，这里转发是为了不依赖
            # 子进程 cwd 下恰好有一份 .env 文件（比如测试里用临时目录起子进程的情况）。
            "env": _forward_env("OPENWEATHER_API_KEY"),
        },
        allowlist={"query_weather", "get_weather_tips"},
        tool_policies={
            "query_weather": ToolPolicy(side_effecting=False, retryable=True, timeout_s=30.0),
            "get_weather_tips": ToolPolicy(side_effecting=False, retryable=True, timeout_s=5.0),
        },
    )

    write = ServerSpec(
        name="write",
        connection={
            "command": python,
            "args": [str(MCP_SERVERS_DIR / "write_server.py")],
            "transport": "stdio",
            "env": _forward_env("WRITE_WORKSPACE_DIR"),
        },
        allowlist={"write_file"},
        tool_policies={
            # 写操作绝不自动重试；重复调用靠幂等键去重，不是靠网关重试掩盖。
            "write_file": ToolPolicy(side_effecting=True, retryable=False, timeout_s=15.0),
        },
    )

    map_server = ServerSpec(
        name="map",
        connection={
            "url": settings.map_mcp_url,
            "transport": "streamable_http",
        },
        allowlist={"geocode", "reverse_geocode"},
        tool_policies={
            "geocode": ToolPolicy(side_effecting=False, retryable=True, timeout_s=10.0),
            "reverse_geocode": ToolPolicy(side_effecting=False, retryable=True, timeout_s=10.0),
        },
    )

    return [weather, write, map_server]
