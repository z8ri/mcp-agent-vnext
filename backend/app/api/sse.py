"""把 `graph.astream(..., stream_mode="updates")` 的 chunk 翻译成 SSE 事件。

不是逐 token 的模型流式（那个留给 Stage E 之后接真实 Key 再验证），
但确实是按图的执行步骤增量推送——工具调用、确认请求、工具结果、最终消息
分别在各自发生的那一刻就发给前端，不是等整轮跑完才一次性返回一个 JSON，
这一点本身已经是相对参考代码"一次性阻塞返回"的真实改进。

事件类型：`tool_call` / `tool_result` / `confirm_required` / `message` / `final` / `error`。
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, AsyncIterator

from langchain_core.messages import AIMessage, ToolMessage

from app.mcp_gateway.contracts import ErrorCode

OnError = Callable[[dict[str, Any]], Awaitable[None]]


def format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_graph_turn(
    graph, run_input, config: dict, *, on_error: OnError | None = None
) -> AsyncIterator[str]:
    try:
        async for chunk in graph.astream(run_input, config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupt_obj = chunk["__interrupt__"][0]
                yield format_sse("confirm_required", dict(interrupt_obj.value))
                continue

            for _node_name, delta in chunk.items():
                if not delta:
                    continue
                for message in delta.get("messages", []) or []:
                    if isinstance(message, AIMessage):
                        if message.tool_calls:
                            for tc in message.tool_calls:
                                yield format_sse(
                                    "tool_call", {"tool": tc["name"], "args": tc["args"], "id": tc["id"]}
                                )
                        elif message.content:
                            yield format_sse("message", {"content": message.content})
                    elif isinstance(message, ToolMessage):
                        try:
                            payload = json.loads(message.content)
                        except (TypeError, ValueError):
                            payload = {"raw": message.content}
                        yield format_sse(
                            "tool_result",
                            {"tool_call_id": message.tool_call_id, "tool": message.name, "result": payload},
                        )
        yield format_sse("final", {})
    except Exception as exc:  # noqa: BLE001 - 流已经开始返回给前端，任何异常都要转成一个 error 事件收尾
        error_payload = {"code": ErrorCode.UNKNOWN.value, "message": str(exc), "retryable": False}
        if on_error is not None:
            # Bad Case 收集（候选架构横切能力里的一项）：真实生产里出现的失败
            # 在这里被记下来，不是只有 eval 里预先写好的 5 个场景才算"案例"。
            await on_error(error_payload)
        yield format_sse("error", error_payload)
