"""脚本化的 Eval 场景。

覆盖不需要真实 API Key 就能跑的几条核心路径：天气工具成功、写文件走
HITL 确认（批准/拒绝两条分支）、无关消息不触发工具、单个 MCP Server
故障不拖垮其它工具。全部用 `MockAgentModel`（关键词触发）驱动真实的
MCP Gateway/Server，不是纯 mock 断言。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    name: str
    description: str
    user_message: str
    broken_servers: list[str] = field(default_factory=list)
    confirm_decision: bool | None = None  # None = 这轮不该出现确认请求
    expect_confirmation_required: bool = False
    expect_executed_tools: list[str] = field(default_factory=list)  # 期望真正执行成功（ok=True）的工具
    expect_not_executed_tools: list[str] = field(default_factory=list)  # 期望没有被执行的工具
    expect_final_contains: str | None = None


CASES: list[EvalCase] = [
    EvalCase(
        name="weather_tip_success",
        description="问天气 -> 触发无副作用的天气工具 -> 不需要确认，直接拿到结果",
        user_message="今天天气怎么样",
        expect_executed_tools=["weather.get_weather_tips"],
        expect_final_contains="成功",
    ),
    EvalCase(
        name="write_confirmed_success",
        description="要求写笔记 -> 先暂停等确认 -> 批准 -> 工具真的执行",
        user_message="帮我写一个笔记",
        confirm_decision=True,
        expect_confirmation_required=True,
        expect_executed_tools=["write.write_file"],
        expect_final_contains="成功",
    ),
    EvalCase(
        name="write_rejected_no_side_effect",
        description="要求写笔记 -> 暂停等确认 -> 拒绝 -> 工具不应该被真正执行",
        user_message="帮我写一个笔记",
        confirm_decision=False,
        expect_confirmation_required=True,
        expect_not_executed_tools=["write.write_file"],
    ),
    EvalCase(
        name="off_topic_no_tool_call",
        description="跟天气/写文件都无关的消息 -> 不应该触发任何工具调用",
        user_message="你好，你是谁？",
        expect_executed_tools=[],
        expect_final_contains="mock",
    ),
    EvalCase(
        name="weather_server_down_write_still_works",
        description="weather server 故障时，write server 应该不受影响仍可用",
        user_message="帮我写一个笔记",
        broken_servers=["weather"],
        confirm_decision=True,
        expect_confirmation_required=True,
        expect_executed_tools=["write.write_file"],
    ),
]
