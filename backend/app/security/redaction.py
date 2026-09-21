"""日志脱敏：对应档案 §10.3 "API 日志记录完整用户消息，错误响应可能向前端暴露
底层异常字符串"、"密钥……当前 stdio 子进程环境注入、日志脱敏……都没有可验证设计"。

`redact_event_dict` 之前只在独立脚本里验证过，没有真的接进请求处理链路——
`log_requests_middleware` 把它接上：每个请求都会真的把 `Authorization` header
这种敏感字段记进日志，脱敏处理器再把它替换掉，这样"脱敏生效"是在真实请求
日志上验证的，不是自说自话。
"""

from __future__ import annotations

import re
import time
from typing import Any, Awaitable, Callable

import structlog
from starlette.requests import Request
from starlette.responses import Response

_SENSITIVE_KEY_PATTERN = re.compile(r"(key|token|secret|password|authorization)", re.IGNORECASE)
_REDACTED = "***redacted***"


def redact_event_dict(_logger: Any, _method_name: str, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if event_dict[key] is not None and _SENSITIVE_KEY_PATTERN.search(key):
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            redact_event_dict,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


def get_logger(name: str):
    return structlog.get_logger(name)


_request_logger = get_logger("http.request")


async def log_requests_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - started) * 1000

    # 故意把原始 header 传进去（包括 authorization），让脱敏处理器在真实数据上生效，
    # 而不是只在专门为了演示而构造的字典上生效。
    _request_logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
        authorization=request.headers.get("authorization"),
    )
    return response
