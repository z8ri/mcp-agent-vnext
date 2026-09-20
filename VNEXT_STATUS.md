# vNext 实现状态

逐项对照求职档案 `PROJECT_DOSSIER.md` 第 11 节候选架构与第 12 节验证清单。只有代码 + 测试都落地才标"已实现"；只有设计没有代码的一律"未开始"。

最后更新：2026-09-20

| 模块 | 对应档案位置 | 状态 | 代码位置 | 测试/验证 |
| --- | --- | --- | --- | --- |
| 仓库脚手架 | - | 进行中 | 根目录 | - |
| MCP Tool Gateway / Registry（allowlist、命名去冲突、schema 校验） | §11 | 未开始 | `backend/app/mcp_gateway/registry.py` | - |
| 超时 / 重试 / 熔断器 | §11 | 未开始 | `backend/app/mcp_gateway/client.py`, `circuit_breaker.py` | - |
| 健康检查 / 单 Server 故障隔离 | §11, §10.2 | 未开始 | `backend/app/mcp_gateway/health.py` | - |
| 幂等键（写类工具去重） | §11, §12.8 | 未开始 | `backend/app/mcp_gateway/idempotency.py` | - |
| Weather Server 重写（重试/缓存/结构化错误） | §7, §10.4 | 未开始 | `mcp_servers/weather_server.py` | - |
| Write Server 重写（路径沙箱、并发防覆盖、幂等） | §7, §12.8 | 未开始 | `mcp_servers/write_server.py` | - |
| 地图 MCP Server（免 Key，替换占位符） | §7, §12.3 | 未开始 | `mcp_servers/map_server.py` | - |
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
