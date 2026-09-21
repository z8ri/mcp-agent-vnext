"""四个手写节点：agent / tools / confirm / finalize。

职责边界（刻意分清这四层，不糊在一起）：
- `agent_node`：Qwen 决定要不要调用工具、调用哪个——纯模型推理。
- `tools_node`：LangGraph 循环控制的一部分，逐个把 tool_call 交给网关；
  网关（MCP Client 协议层）决定要不要真的转发给 MCP Server 执行。
- `confirm_node`：HITL 门控，真正暂停图的执行等人确认，不是网关内部状态。
- `finalize_node`：收尾。

Trace 只包在真正执行一次的工作上——`model.ainvoke()`、
`gateway.call()`——不包 `interrupt()` 本身：`interrupt()` 暂停时会向上抛
`GraphInterrupt`，而且恢复执行时整个节点函数会从头重新跑一遍；把这段也包进
span 会导致"暂停"被错误记成一次 error，恢复时又会多记一条重复 span。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.runnables.config import RunnableConfig
from langgraph.types import interrupt

from app.mcp_gateway.client import GatewayClient
from app.mcp_gateway.contracts import ErrorCode
from app.agent.state import AgentState, PendingToolCall
from app.trace.tracer import Tracer


def _thread_id(config: RunnableConfig) -> str:
    return config["configurable"]["thread_id"]


def _record_token_usage(attrs: dict[str, Any], response: AIMessage) -> None:
    # `ChatTongyi` 不走 LangChain 标准的 `usage_metadata` 字段（实测是 None），
    # token 用量在 `response_metadata["token_usage"]` 里——这是真的调真实通义
    # 千问核实过的，不是照着文档猜的字段名。别的模型/mock 模型没有这个字段时
    # 就不记，budget 那边会把它当成 0 token 处理，不是当成报错。
    usage = response.response_metadata.get("token_usage") if response.response_metadata else None
    if usage:
        attrs["input_tokens"] = usage.get("input_tokens", 0)
        attrs["output_tokens"] = usage.get("output_tokens", 0)


def _record_result(attrs: dict[str, Any], result) -> None:
    # 只记 ok/error code，不把工具的 args/content 写进 trace——那可能是用户输入的原文。
    attrs["ok"] = result.ok
    attrs["idempotent_replay"] = result.idempotent_replay
    if result.error is not None:
        attrs["error_code"] = result.error.code.value

SYSTEM_PROMPT = (
    "你是一个可以调用工具的助手。工具名里的前缀（比如 write. 或 weather.）表示"
    "它属于哪个 MCP Server，直接按工具名调用即可，不需要向用户解释这个前缀。"
    "涉及写文件这类有副作用的操作，系统会在真正执行前单独向用户确认，"
    "你不需要自己再问一遍\"确定要写吗\"。"
)


def make_agent_node(model_with_tools: Runnable, tracer: Tracer | None = None):
    async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]

        if tracer is None:
            response = await model_with_tools.ainvoke(messages)
        else:
            async with tracer.span(_thread_id(config), "agent.invoke", message_count=len(messages)) as attrs:
                response = await model_with_tools.ainvoke(messages)
                _record_token_usage(attrs, response)

        assert isinstance(response, AIMessage)

        queue: list[PendingToolCall] = [
            {"id": tc["id"], "name": tc["name"], "args": tc["args"]} for tc in (response.tool_calls or [])
        ]
        return {"messages": [response], "tool_call_queue": queue, "awaiting_confirmation": None}

    return agent_node


def route_after_agent(state: AgentState) -> str:
    return "tools" if state["tool_call_queue"] else "finalize"


def make_tools_node(gateway: GatewayClient, tracer: Tracer | None = None):
    async def tools_node(state: AgentState, config: RunnableConfig) -> dict:
        queue = list(state["tool_call_queue"])
        call = queue.pop(0)

        if tracer is None:
            result = await gateway.call(call["name"], call["args"], confirmed=False, idempotency_key=call["id"])
        else:
            async with tracer.span(_thread_id(config), f"tool.call:{call['name']}", confirmed=False) as attrs:
                result = await gateway.call(call["name"], call["args"], confirmed=False, idempotency_key=call["id"])
                _record_result(attrs, result)

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


def make_confirm_node(gateway: GatewayClient, tracer: Tracer | None = None):
    async def confirm_node(state: AgentState, config: RunnableConfig) -> dict:
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

        if tracer is None:
            result = await gateway.call(
                pending["name"], pending["args"], confirmed=True, idempotency_key=pending["id"]
            )
        else:
            async with tracer.span(_thread_id(config), f"tool.call:{pending['name']}", confirmed=True) as attrs:
                result = await gateway.call(
                    pending["name"], pending["args"], confirmed=True, idempotency_key=pending["id"]
                )
                _record_result(attrs, result)

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
    # 目前是空操作；如果之后要给"整轮对话"本身加一个收尾 span，挂在这里。
    return {}
