"""网关层的统一工具调用契约。

参考代码里工具直接返回一段格式化文本，异常也当成普通字符串糊给模型；
这里把"结果"和"错误"拆开，错误带 code/retryable，让网关的重试、熔断、
前端的分级错误展示都能基于结构化信息做决定，而不是解析文本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    TIMEOUT = "timeout"
    TRANSPORT = "transport"          # MCP 连接/传输层失败（进程起不来、HTTP 连不上）
    PROTOCOL = "protocol"            # MCP 协议错误（isError、schema 不合法）
    PROVIDER = "provider"            # 工具背后的外部 Provider（OpenWeather/Nominatim）失败
    NOT_ALLOWED = "not_allowed"      # 命中 allowlist/Registry 拒绝
    CIRCUIT_OPEN = "circuit_open"    # 熔断器处于打开状态，直接短路
    CONFIRMATION_REQUIRED = "confirmation_required"
    VALIDATION = "validation"        # 入参不合法（比如路径穿越）
    UNKNOWN = "unknown"


@dataclass
class ToolError:
    code: ErrorCode
    message: str
    retryable: bool = False


@dataclass
class ToolResult:
    ok: bool
    server: str
    tool: str
    data: Any = None
    error: ToolError | None = None
    from_cache: bool = False
    idempotent_replay: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, server: str, tool: str, data: Any, **kwargs) -> "ToolResult":
        return cls(ok=True, server=server, tool=tool, data=data, **kwargs)

    @classmethod
    def failure(cls, server: str, tool: str, error: ToolError, **kwargs) -> "ToolResult":
        return cls(ok=False, server=server, tool=tool, error=error, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "server": self.server,
            "tool": self.tool,
            "from_cache": self.from_cache,
            "idempotent_replay": self.idempotent_replay,
        }
        if self.ok:
            out["data"] = self.data
        else:
            assert self.error is not None
            out["error"] = {
                "code": self.error.code.value,
                "message": self.error.message,
                "retryable": self.error.retryable,
            }
        if self.attributes:
            out["attributes"] = self.attributes
        return out
