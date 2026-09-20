"""跑 `cases.py` 里的场景，产出一份可读的回归报告。

每个用例用独立的临时目录（隔离的 workspace/idempotency db/trace db/checkpoint db），
互不干扰；`MOCK_MODE` 不依赖环境变量，直接强制用 `MockAgentModel`，
所以这份报告在没有任何 API Key 的机器上也能跑。

用法：`python -m eval.runner`（cwd 在 backend/ 下）。
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.agent.checkpointer import sqlite_checkpointer
from app.agent.graph import build_graph
from app.agent.mock_model import MockAgentModel
from app.mcp_gateway.client import GatewayClient
from app.mcp_gateway.idempotency import IdempotencyStore
from app.mcp_gateway.registry import ServerRegistry
from app.mcp_gateway.server_specs import MCP_SERVERS_DIR, default_server_specs
from app.trace.tracer import Tracer
from eval.cases import CASES, EvalCase


@dataclass
class EvalResult:
    case: EvalCase
    passed: bool
    failures: list[str]
    duration_ms: float
    spans: list[dict]


def _break_spec(spec):
    broken_connection = dict(spec.connection)
    broken_connection["args"] = [str(MCP_SERVERS_DIR / "does_not_exist.py")]
    return replace(spec, connection=broken_connection)


async def run_case(case: EvalCase) -> EvalResult:
    started = time.monotonic()
    failures: list[str] = []
    spans: list[dict] = []

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # write_server 是独立子进程，转发环境变量的白名单在 discover_all() 真正
        # spawn 子进程时才生效，所以必须在拿到 specs 之前就设好这个环境变量。
        os.environ["WRITE_WORKSPACE_DIR"] = str(tmp_path / "workspace")
        specs = [s for s in default_server_specs() if s.name in ("weather", "write")]
        specs = [_break_spec(s) if s.name in case.broken_servers else s for s in specs]

        registry = ServerRegistry(specs)
        await registry.discover_all()
        gateway = GatewayClient(registry, IdempotencyStore(db_path=str(tmp_path / "idempotency.sqlite3")))
        tracer = Tracer(db_path=str(tmp_path / "trace.sqlite3"))
        thread_id = f"eval-{case.name}-{uuid.uuid4().hex[:8]}"

        try:
            async with sqlite_checkpointer(str(tmp_path / "checkpoints.sqlite3")) as checkpointer:
                graph = build_graph(MockAgentModel(), gateway, checkpointer, tracer=tracer)
                config = {"configurable": {"thread_id": thread_id}}

                state = {
                    "messages": [HumanMessage(content=case.user_message)],
                    "tool_call_queue": [],
                    "awaiting_confirmation": None,
                }
                result = await graph.ainvoke(state, config)
                was_paused = bool(result.get("__interrupt__"))

                if was_paused != case.expect_confirmation_required:
                    failures.append(
                        f"expect_confirmation_required={case.expect_confirmation_required}，实际 paused={was_paused}"
                    )

                if was_paused:
                    if case.confirm_decision is None:
                        failures.append("图暂停等待确认，但用例没有提供 confirm_decision")
                    else:
                        result = await graph.ainvoke(Command(resume={"approved": case.confirm_decision}), config)

                final_messages = result.get("messages", [])
                final_text = final_messages[-1].content if final_messages else ""
                if case.expect_final_contains and case.expect_final_contains not in final_text:
                    failures.append(f"最终消息里没有包含 {case.expect_final_contains!r}：{final_text!r}")
        finally:
            spans = await tracer.spans_for_thread(thread_id)
            await registry.close()

        executed_ok = {
            s["name"].removeprefix("tool.call:")
            for s in spans
            if s["name"].startswith("tool.call:") and s["attributes"].get("ok") is True
        }
        for tool in case.expect_executed_tools:
            if tool not in executed_ok:
                failures.append(f"期望 {tool} 执行成功，但没有看到对应的成功 span")
        for tool in case.expect_not_executed_tools:
            if tool in executed_ok:
                failures.append(f"期望 {tool} 不应该被执行，但看到了成功执行的 span")

    duration_ms = (time.monotonic() - started) * 1000
    return EvalResult(case=case, passed=not failures, failures=failures, duration_ms=duration_ms, spans=spans)


async def run_all(cases: list[EvalCase] | None = None) -> list[EvalResult]:
    results = []
    for case in cases if cases is not None else CASES:
        results.append(await run_case(case))
    return results


def format_report(results: list[EvalResult]) -> str:
    passed = sum(1 for r in results if r.passed)
    lines = [f"Eval 结果：{passed}/{len(results)} 通过", ""]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"[{status}] {r.case.name} ({r.duration_ms:.0f}ms) - {r.case.description}")
        for failure in r.failures:
            lines.append(f"    - {failure}")
    return "\n".join(lines)


if __name__ == "__main__":
    results = asyncio.run(run_all())
    print(format_report(results))
    raise SystemExit(0 if all(r.passed for r in results) else 1)
