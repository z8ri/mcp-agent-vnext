"""日志脱敏：对应档案 §10.3 "API 日志记录完整用户消息，错误响应可能向前端暴露
底层异常字符串"、"密钥……当前 stdio 子进程环境注入、日志脱敏……都没有可验证设计"。
"""

from __future__ import annotations

import re
from typing import Any

import structlog

_SENSITIVE_KEY_PATTERN = re.compile(r"(key|token|secret|password|authorization)", re.IGNORECASE)
_REDACTED = "***redacted***"


def redact_event_dict(_logger: Any, _method_name: str, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if _SENSITIVE_KEY_PATTERN.search(key):
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
