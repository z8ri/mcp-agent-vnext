"""自定义 LangGraph 图的端到端测试。

用 `FakeMessagesListChatModel` 脚本化模型的回复（不需要 DASHSCOPE_API_KEY），
但网关和 MCP Server 是真实的——真的启动 weather/write 子进程、真的写文件、
真的通过 `interrupt()`/`Command` 走一次完整的 HITL 暂停/恢复。

这两个用例直接对应求职档案 §9 偏差 1（手写节点/条件边 vs 预构建 Agent）和
§12.5/§12.8（多步骤 Trace、写文件确认与幂等）的验证要求。
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.agent.checkpointer import sqlite_checkpointer
from app.agent.graph import build_graph
from app.mcp_gateway.client import GatewayClient
from app.mcp_gateway.idempotency import IdempotencyStore
from app.mcp_gateway.registry import ServerRegistry
from app.mcp_gateway.server_specs import default_server_specs


@pytest_asyncio.fixture
async def real_gateway(tmp_path, monkeypatch):
    # write_server.py 是独立子进程，模块加载时读一次 WRITE_WORKSPACE_DIR；
    # 必须在 discover_all() 真正 spawn 子进程之前设好这个环境变量，子进程才能继承到。
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("WRITE_WORKSPACE_DIR", str(workspace))

    specs = [s for s in default_server_specs() if s.name in ("weather", "write")]
    registry = ServerRegistry(specs)
    await registry.discover_all()
    gateway = GatewayClient(registry, IdempotencyStore(db_path=str(tmp_path / "idempotency.sqlite3")))
    yield gateway, workspace
    await registry.close()


@pytest.mark.asyncio
async def test_write_tool_pauses_for_confirmation_then_executes(real_gateway, tmp_path):
    gateway, workspace = real_gateway

    fake_model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write.write_file",
                        "args": {"content": "graph test", "path": "graph_smoke.txt"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="已经帮你写好文件了。"),
        ]
    )

    async with sqlite_checkpointer(str(tmp_path / "checkpoints.sqlite3")) as checkpointer:
        graph = build_graph(fake_model, gateway, checkpointer)
        config = {"configurable": {"thread_id": "test-thread-1"}}
        initial_state = {
            "messages": [HumanMessage(content="帮我写一个笔记")],
            "tool_call_queue": [],
            "awaiting_confirmation": None,
        }

        paused = await graph.ainvoke(initial_state, config)
        assert paused.get("__interrupt__"), "有副作用的工具调用应该让图在 confirm 节点暂停"
        assert not (workspace / "graph_smoke.txt").exists(), "确认前不应该真的写文件"

        resumed = await graph.ainvoke(Command(resume={"approved": True}), config)
        assert resumed["messages"][-1].content == "已经帮你写好文件了。"
        assert (workspace / "graph_smoke.txt").read_text(encoding="utf-8") == "graph test"


@pytest.mark.asyncio
async def test_rejecting_confirmation_skips_the_write(real_gateway, tmp_path):
    gateway, workspace = real_gateway

    fake_model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "weather.get_weather_tips",
                        "args": {"season": "spring"},
                        "id": "call_a",
                        "type": "tool_call",
                    },
                    {
                        "name": "write.write_file",
                        "args": {"content": "should not be written", "path": "should_not_exist.txt"},
                        "id": "call_b",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="好的，已了解，没有写文件。"),
        ]
    )

    async with sqlite_checkpointer(str(tmp_path / "checkpoints.sqlite3")) as checkpointer:
        graph = build_graph(fake_model, gateway, checkpointer)
        config = {"configurable": {"thread_id": "test-thread-2"}}
        initial_state = {
            "messages": [HumanMessage(content="给我个建议但别写文件")],
            "tool_call_queue": [],
            "awaiting_confirmation": None,
        }

        paused = await graph.ainvoke(initial_state, config)
        assert paused.get("__interrupt__")
        # 队列里排在前面的、没有副作用的天气工具应该已经在暂停前执行完
        tool_messages = [m for m in paused["messages"] if m.__class__.__name__ == "ToolMessage"]
        assert len(tool_messages) == 1

        resumed = await graph.ainvoke(Command(resume={"approved": False}), config)
        assert resumed["messages"][-1].content == "好的，已了解，没有写文件。"
        assert not os.path.exists(workspace / "should_not_exist.txt")
