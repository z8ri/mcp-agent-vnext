"""write_server.py 的路径沙箱与幂等文件名逻辑测试。

`WORKSPACE_ROOT` 是 write_server 模块加载时读一次环境变量决定的全局值，
所以这里在 import 之前先设好 `WRITE_WORKSPACE_DIR`，再动态加载模块，
保证每个测试用例用互相隔离的临时目录，不会碰到真实的 output/ 目录。

注：假设 `@mcp.tool()` 装饰器不改变被装饰函数本身（可以直接 await 调用），
这是目前主流 FastMCP 版本的行为；如果装了依赖后发现不成立，这个假设需要更新。
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

MCP_SERVERS_DIR = str(Path(__file__).resolve().parents[1])


def _load_write_server(workspace_dir: Path):
    if MCP_SERVERS_DIR not in sys.path:
        sys.path.insert(0, MCP_SERVERS_DIR)
    os.environ["WRITE_WORKSPACE_DIR"] = str(workspace_dir)
    if "write_server" in sys.modules:
        return importlib.reload(sys.modules["write_server"])
    import write_server  # noqa: PLC0415

    return write_server


def test_relative_path_resolves_inside_workspace(tmp_path):
    ws = _load_write_server(tmp_path)
    resolved = ws._resolve_safe_path("notes/a.txt", "hello")
    assert resolved == (tmp_path / "notes/a.txt").resolve()


def test_parent_traversal_is_rejected(tmp_path):
    ws = _load_write_server(tmp_path)
    result = ws._resolve_safe_path("../outside.txt", "hello")
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error"]["code"] == "validation"


def test_absolute_path_escaping_workspace_is_rejected(tmp_path):
    ws = _load_write_server(tmp_path)
    result = ws._resolve_safe_path("/etc/passwd", "hello")
    assert isinstance(result, dict)
    assert result["ok"] is False


def test_auto_generated_filenames_do_not_collide(tmp_path):
    ws = _load_write_server(tmp_path)
    a = ws._resolve_safe_path(None, "same content")
    b = ws._resolve_safe_path(None, "same content")
    assert a.parent == tmp_path
    assert a.name != b.name


@pytest.mark.asyncio
async def test_write_file_does_not_overwrite_by_default(tmp_path):
    ws = _load_write_server(tmp_path)

    first = await ws.write_file(content="v1", path="a.txt")
    assert first["ok"] is True
    assert first["data"]["skipped_existing"] is False
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "v1"

    second = await ws.write_file(content="v2", path="a.txt")
    assert second["ok"] is True
    assert second["data"]["skipped_existing"] is True
    # 没有 overwrite=True，文件内容应该还是第一次写入的内容
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "v1"


@pytest.mark.asyncio
async def test_write_file_overwrites_when_explicitly_requested(tmp_path):
    ws = _load_write_server(tmp_path)

    await ws.write_file(content="v1", path="a.txt")
    second = await ws.write_file(content="v2", path="a.txt", overwrite=True)

    assert second["ok"] is True
    assert second["data"]["skipped_existing"] is False
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "v2"
