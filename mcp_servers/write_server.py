"""Write MCP Server。

- 接收调用方传入的相对 `path`，做路径穿越校验，写入范围锁定在工作区目录内；
- 文件名不再只精确到秒——没传 `path` 时用内容哈希 + 短 uuid 生成，避免同秒并发覆盖；
- 默认不覆盖已存在文件（`overwrite=False`），已存在就返回 `skipped_existing`，
  调用方（Agent 图的 confirm 节点 + 网关幂等键）负责决定要不要真的覆盖；
- 进程内用 per-path 锁串行化并发写同一文件，跨进程/跨副本的并发仍需要外部协调，
  这里不假装解决了那一层。

是否真的执行写入由上层网关的 HITL 确认门控（Agent 图的 confirm 节点），
这个 Server 本身不做用户确认弹窗——Server 只管契约和领域执行。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from common import err, ok

mcp = FastMCP("WriteServer")

WORKSPACE_ROOT = Path(os.getenv("WRITE_WORKSPACE_DIR", "./output")).resolve()
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

_write_locks: dict[Path, asyncio.Lock] = {}


def _lock_for(path: Path) -> asyncio.Lock:
    return _write_locks.setdefault(path, asyncio.Lock())


def _resolve_safe_path(requested_path: str | None, content: str) -> Path | dict:
    """把调用方给的 path 解析到工作区内；越界或非法就返回结构化错误字典。"""
    if requested_path:
        candidate = (WORKSPACE_ROOT / requested_path).resolve()
        try:
            candidate.relative_to(WORKSPACE_ROOT)
        except ValueError:
            return err("validation", f"path 越出工作区范围: {requested_path}", retryable=False)
        return candidate

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    filename = f"note_{digest}_{uuid.uuid4().hex[:8]}.txt"
    return WORKSPACE_ROOT / filename


@mcp.tool()
async def write_file(content: str, path: str | None = None, overwrite: bool = False) -> dict:
    """
    将内容写入工作区内的文件。

    :param content: 要写入的文本内容。
    :param path: 工作区内的相对路径（可选）；不传则按内容哈希自动生成文件名。
                 不允许越出工作区（比如 "../secret.txt"）。
    :param overwrite: 目标文件已存在时是否覆盖，默认 False。
    :return: {"ok": true, "data": {"path", "bytes_written", "skipped_existing"}}
             或 {"ok": false, "error": {...}}。
    """
    resolved = _resolve_safe_path(path, content)
    if isinstance(resolved, dict):
        return resolved

    async with _lock_for(resolved):
        if resolved.exists() and not overwrite:
            return ok(
                {
                    "path": str(resolved.relative_to(WORKSPACE_ROOT)),
                    "bytes_written": 0,
                    "skipped_existing": True,
                }
            )

        tmp_path = resolved.with_suffix(resolved.suffix + f".tmp-{uuid.uuid4().hex[:8]}")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, resolved)
        except OSError as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return err("provider", f"写入失败: {exc}", retryable=False)

    return ok(
        {
            "path": str(resolved.relative_to(WORKSPACE_ROOT)),
            "bytes_written": len(content.encode("utf-8")),
            "skipped_existing": False,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
