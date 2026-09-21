"""`MOCK_MODE=true` 时用的假模型：不需要 DASHSCOPE_API_KEY 也能把全链路跑起来。

按关键词决定要不要调用工具，纯粹是为了在没有真实 Key 的时候验证
"Vue -> FastAPI -> Agent 图 -> MCP Gateway -> MCP Server" 这条链路是通的，
不代表真实的模型推理能力——这一点在 README 里说清楚，不能让人误以为
这是个真正智能的对话模型。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class MockAgentModel(BaseChatModel):
    """关键词触发工具调用的假模型，配合真实 MCP Gateway/Server 联调用。"""

    @property
    def _llm_type(self) -> str:
        return "mock-agent-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1]

        if isinstance(last, ToolMessage):
            message = AIMessage(content=_summarize_tool_result(last.content))
            return ChatResult(generations=[ChatGeneration(message=message)])

        text = last.content if isinstance(last.content, str) else str(last.content)
        tool_call = _infer_tool_call(text)
        if tool_call is not None:
            message = AIMessage(content="", tool_calls=[tool_call])
        else:
            message = AIMessage(content=f"（mock 模式回复，未配置真实模型）收到：{text}")
        return ChatResult(generations=[ChatGeneration(message=message)])


def _summarize_tool_result(raw_content: str) -> str:
    try:
        payload = json.loads(raw_content)
    except (TypeError, ValueError):
        return "工具已执行，但返回内容不是预期的 JSON 格式。"

    if payload.get("ok"):
        return "工具调用成功。"
    error = payload.get("error") or {}
    return f"工具调用失败：{error.get('message', '未知错误')}"


def _infer_tool_call(text: str) -> dict | None:
    lowered = text.lower()
    call_id = uuid.uuid4().hex

    if "写" in text or "write" in lowered:
        return {
            "name": "write.write_file",
            "args": {"content": text},
            "id": call_id,
            "type": "tool_call",
        }

    if "天气" in text or "weather" in lowered:
        return {
            "name": "weather.get_weather_tips",
            "args": {"season": "summer"},
            "id": call_id,
            "type": "tool_call",
        }

    return None
