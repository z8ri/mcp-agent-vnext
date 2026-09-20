"""自定义 LangGraph 状态。

对应求职档案 §9 偏差 1："声称手工定义模型节点、工具节点、结果节点和条件边；
源码只调用预构建 create_react_agent"。这里是真的手写状态和节点，不是套壳。

`tool_call_queue` / `awaiting_confirmation` 是为了处理"模型一次返回多个 tool_call，
其中一个是有副作用要走 HITL 确认，其余先执行"这种真实场景——预构建的
`create_react_agent` 是把一批 tool_call 一次性并发执行完，没有这种细粒度控制点。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class PendingToolCall(TypedDict):
    id: str
    name: str          # qualified name，比如 "write.write_file"
    args: dict[str, Any]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_call_queue: list[PendingToolCall]
    awaiting_confirmation: PendingToolCall | None


ConfirmationDecision = Literal["approved", "rejected"]
