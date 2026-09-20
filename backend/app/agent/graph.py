"""手写的 LangGraph 状态图。

条件边（对应档案 §9 偏差 1 要求的"手工定义……条件边"）：

    START -> agent
    agent -> tools    （本轮模型产生了 tool_call）
    agent -> finalize （没有 tool_call，可以收尾）
    tools -> confirm  （弹出的这个 tool_call 有副作用且未确认）
    tools -> tools    （还有排队的 tool_call 没处理）
    tools -> agent    （这一批 tool_call 都处理完了，交回模型）
    confirm -> tools  （确认/拒绝后，继续处理队列里剩下的 tool_call）
    confirm -> agent  （队列已空，交回模型）
    finalize -> END
"""

from __future__ import annotations

from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    finalize_node,
    make_agent_node,
    make_confirm_node,
    make_tools_node,
    route_after_agent,
    route_after_confirm,
    route_after_tools,
)
from app.agent.state import AgentState
from app.mcp_gateway.client import GatewayClient


def build_graph(model_with_tools: Runnable, gateway: GatewayClient, checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)

    builder.add_node("agent", make_agent_node(model_with_tools))
    builder.add_node("tools", make_tools_node(gateway))
    builder.add_node("confirm", make_confirm_node(gateway))
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "finalize": "finalize"})
    builder.add_conditional_edges("tools", route_after_tools, {"confirm": "confirm", "tools": "tools", "agent": "agent"})
    builder.add_conditional_edges("confirm", route_after_confirm, {"tools": "tools", "agent": "agent"})
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)


def build_default_agent_graph(gateway: GatewayClient, checkpointer: BaseCheckpointSaver, *, model: Runnable | None = None):
    """真实运行时用的入口：拿真实 ChatTongyi，绑定网关暴露的工具。"""
    if model is None:
        from langchain_community.chat_models import ChatTongyi

        from app.config import get_settings

        settings = get_settings()
        model = ChatTongyi(model=settings.qwen_model, dashscope_api_key=settings.dashscope_api_key, streaming=True)

    model_with_tools = model.bind_tools(gateway.registry.bindable_tools())
    return build_graph(model_with_tools, gateway, checkpointer)
