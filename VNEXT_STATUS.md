# vNext 实现状态

逐项对照求职档案 `PROJECT_DOSSIER.md` 第 11 节候选架构与第 12 节验证清单。只有代码 + 测试都落地才标"已实现"；只有设计没有代码的一律"未开始"。

最后更新：2026-09-20

**环境限制**：本机只有 Python 3.9，而 `mcp` / `langgraph` 等依赖要求 3.10+，无法在本机安装依赖、跑真实 pytest 套件或起真实进程验证。下表里"进行中"的模块是"代码已写完、语法检查通过、关键逻辑用不依赖第三方包的手写脚本单独验证过"，不等于"pytest 套件已跑绿"——这两者的区别在"测试/验证"列里写清楚，避免和已经真正跑通的模块混在一起。用户装好 Python 3.11+ 环境后，跑 `pytest` 就是把这些"进行中"升级成"已实现"的下一步。

| 模块 | 对应档案位置 | 状态 | 代码位置 | 测试/验证 |
| --- | --- | --- | --- | --- |
| 仓库脚手架 | - | 已完成 | 根目录 | - |
| MCP Tool Gateway / Registry（allowlist、命名去冲突、schema 校验） | §11 | 进行中 | `backend/app/mcp_gateway/registry.py` | 代码完成；依赖 `langchain-mcp-adapters` 未装，未跑真实发现流程 |
| 超时 / 重试 / 熔断器 | §11 | 进行中 | `backend/app/mcp_gateway/client.py`, `circuit_breaker.py` | 熔断器状态机已用独立脚本手动跑通（`backend/tests/test_circuit_breaker.py` 逻辑已核对，pytest 未跑）；重试/超时链路依赖真实工具调用，未验证 |
| 健康检查 / 单 Server 故障隔离 | §11, §10.2 | 进行中 | `backend/app/mcp_gateway/health.py` | 代码完成，未跑（依赖真实 MCP 连接） |
| 幂等键（写类工具去重） | §11, §12.8 | 进行中 | `backend/app/mcp_gateway/idempotency.py` | 代码完成，`backend/tests/test_idempotency.py` 已写但需要 `aiosqlite`+`pytest-asyncio`，本机未跑 |
| Weather Server 重写（重试/缓存/结构化错误） | §7, §10.4 | 进行中 | `mcp_servers/weather_server.py` | 代码完成、语法检查通过；无 OPENWEATHER_API_KEY，未跑真实/mock HTTP 请求验证 |
| Write Server 重写（路径沙箱、并发防覆盖、幂等） | §7, §12.8 | 进行中 | `mcp_servers/write_server.py` | 路径穿越校验 + 覆盖/跳过语义已用独立脚本手动跑通（对应 `mcp_servers/tests/test_write_server.py`），pytest 本身未跑 |
| 地图 MCP Server（免 Key，替换占位符） | §7, §12.3 | 进行中 | `mcp_servers/map_server.py` | 代码完成；`mcp.run(transport="streamable-http")` 的具体参数未装 `mcp` 包验证，见文件内注释 |
| 自定义 LangGraph 图（agent/tools/confirm/finalize 节点与条件边） | §9 偏差 1, §11 | 未开始 | `backend/app/agent/graph.py`, `nodes.py`, `state.py` | - |
| SQLite Checkpointer（替换 InMemorySaver） | §10.1 | 未开始 | `backend/app/agent/checkpointer.py` | - |
| 流式修复（`astream_events` 正确处理增量片段） | §9 偏差 4 | 未开始 | `backend/app/agent/graph.py` | - |
| JWT 鉴权 + 用户表 | §11 | 未开始 | `backend/app/auth/` | - |
| SessionManager（user→conversation→thread，同 thread 并发锁） | §10.1, §11 | 未开始 | `backend/app/sessions/manager.py` | - |
| FastAPI SSE `/chat`、分级错误事件 | §11 | 未开始 | `backend/app/api/routes_chat.py` | - |
| `/healthz` `/readyz` | §11 | 未开始 | `backend/app/api/routes_admin.py` | - |
| CORS 白名单 / 限流 / 日志脱敏 | §10.3 | 未开始 | `backend/app/api/`, `backend/app/security/` | - |
| Trace（结构化 span） | §11 | 未开始 | `backend/app/trace/tracer.py` | - |
| Eval 回归场景（mock 模式可跑） | §12 | 未开始 | `backend/tests/eval_cases/` | - |
| Vue3 前端（真实 thread_id、SSE 消费、语法高亮、分级错误+重试、HITL 确认卡） | §9 偏差 5-6, §11 | 未开始 | `frontend/src/` | - |
| Playwright E2E | §12.9 | 未开始 | `frontend/e2e/` | - |
| Docker Compose 本地部署 | §11 | 未开始 | `ops/docker-compose.yml` | - |

## 说明

- "状态"只有三档：未开始 / 进行中 / 已实现（代码+测试）。不写"已设计"，避免和档案里"候选设计 ≠ 已实现"的区分混淆。
- 本文件不会跨仓库修改求职档案 `PROJECT_DOSSIER.md`；更新那份档案是用户自己的后续任务，这里只提供可引用的证据清单。
