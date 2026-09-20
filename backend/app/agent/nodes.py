"""四个手写节点：agent / tools / confirm / finalize。

职责边界（对应求职档案 §6 要求分清的四层）：
- `agent_node`：Qwen 决定要不要调用工具、调用哪个——纯模型推理。
- `tools_node`：LangGraph 循环控制的一部分，逐个把 tool_call 交给网关；
  网关（MCP Client 协议层）决定要不要真的转发给 MCP Server 执行。
- `confirm_node`：HITL 门控，真正暂停图的执行等人确认，不是网关内部状态。
- `finalize_node`：收尾，给 Stage F 的 Trace 关闭点留一个挂载位置。
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.types import interrupt

from app.mcp_gateway.client import GatewayClient
from app.mcp_gateway.contracts import ErrorCode
from app.agent.state import AgentState, PendingToolCall

SYSTEM_PROMPT = (
    "你是一个可以调用工具的助手。工具名里的前缀（比如 write. 或 weather.）表示"
    "它属于哪个 MCP Server，直接按工具名调用即可，不需要向用户解释这个前缀。"
    "涉及写文件这类有副作用的操作，系统会在真正执行前单独向用户确认，"
    "你不需要自己再问一遍\"确定要写吗\"。"
)


def make_agent_node(model_with_tools: Runnable):
    async def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = await model_with_tools.ainvoke(messages)
        assert isinstance(response, AIMessage)

        queue: list[PendingToolCall] = [
            {"id": tc["id"], "name": tc["name"], "args": tc["args"]} for tc in (response.tool_calls or [])
        ]
        return {"messages": [response], "tool_call_queue": queue, "awaiting_confirmation": None}

    return agent_node


def route_after_agent(state: AgentState) -> str:
    return "tools" if state["tool_call_queue"] else "finalize"


def make_tools_node(gateway: GatewayClient):
    async def tools_node(state: AgentState) -> dict:
        queue = list(state["tool_call_queue"])
        call = queue.pop(0)

        result = await gateway.call(call["name"], call["args"], confirmed=False, idempotency_key=call["id"])

        if not result.ok and result.error is not None and result.error.code == ErrorCode.CONFIRMATION_REQUIRED:
            return {"tool_call_queue": queue, "awaiting_confirmation": call}

        tool_message = ToolMessage(
            content=json.dumps(result.to_dict(), ensure_ascii=False),
            tool_call_id=call["id"],
            name=call["name"],
        )
        return {"messages": [tool_message], "tool_call_queue": queue, "awaiting_confirmation": None}

    return tools_node


def route_after_tools(state: AgentState) -> str:
    if state["awaiting_confirmation"] is not None:
        return "confirm"
    return "tools" if state["tool_call_queue"] else "agent"


def make_confirm_node(gateway: GatewayClient):
    async def confirm_node(state: AgentState) -> dict:
        pending = state["awaiting_confirmation"]
        assert pending is not None

        decision = interrupt(
            {
                "type": "confirm_tool_call",
                "tool": pending["name"],
                "args": pending["args"],
                "tool_call_id": pending["id"],
            }
        )
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)

        if not approved:
            rejection = ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": ErrorCode.CONFIRMATION_REQUIRED.value,
                            "message": "用户拒绝执行该操作",
                            "retryable": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                tool_call_id=pending["id"],
                name=pending["name"],
            )
            return {"messages": [rejection], "awaiting_confirmation": None}

        result = await gateway.call(pending["name"], pending["args"], confirmed=True, idempotency_key=pending["id"])
        tool_message = ToolMessage(
            content=json.dumps(result.to_dict(), ensure_ascii=False),
            tool_call_id=pending["id"],
            name=pending["name"],
        )
        return {"messages": [tool_message], "awaiting_confirmation": None}

    return confirm_node


def route_after_confirm(state: AgentState) -> str:
    return "tools" if state["tool_call_queue"] else "agent"


async def finalize_node(state: AgentState) -> dict:
    # Stage F 会在这里挂载 Trace span 收尾；现在先保持空操作。
    return {}
