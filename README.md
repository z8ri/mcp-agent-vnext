# MCP Agent vNext

基于 MCP 多服务 + LangGraph 自定义图 + FastAPI + Vue3 的多工具 ReAct Agent，独立实现（JHU 2026 春季个人课程作业）。

这是对某求职机构提供的教学参考代码（`weather`/`write` 两个本地 MCP Server + LangGraph 预构建 ReAct Agent + Vue 单页聊天界面）的独立重写和扩展，目标是把参考代码中的教学简化点，实现为真正可运行、可验证的完整系统：

- 自定义 LangGraph 状态图（而不是预构建 `create_react_agent`），显式区分 agent / tools / confirm(HITL) / finalize 节点
- MCP Tool Gateway：allowlist、超时、重试、熔断、健康检查、幂等键、单 Server 故障隔离
- 真实多用户会话隔离：JWT 登录 + SessionManager（user → conversation → LangGraph thread）+ 同 thread 并发锁
- SQLite Checkpointer（跨重启恢复），而不是进程内 `InMemorySaver`
- 真实 SSE 流式输出，修复参考代码中"关闭流式规避错误"的问题
- 自建免 Key 地图 MCP Server（基于 OpenStreetMap Nominatim），替换参考代码中的占位符地图配置
- 结构化 Trace / Eval 回归测试，可在没有真实 API Key 的情况下用 mock 模式跑通

## 目录结构

```
backend/        FastAPI 应用、Agent Harness、MCP Gateway、鉴权、数据库模型
mcp_servers/    独立的 MCP Server 进程（weather / write / map）
frontend/       Vue3 前端
ops/            Docker Compose 与部署配置
```

## 状态

项目搭建中，详见 [VNEXT_STATUS.md](VNEXT_STATUS.md) 追踪各模块的实现进度。

## 环境要求

- **Python 3.11+**（`mcp`、`langgraph-checkpoint-sqlite` 等依赖要求 3.10+；本仓库的代码是在没有 3.10+ 环境的机器上写的，还没有用真实依赖跑过，见 `VNEXT_STATUS.md` 里每个模块的验证状态）。
- Node.js 18+（前端，Stage G 会补充版本锁定）。

## 快速开始（后端，MCP Gateway 部分）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # 按需填 Key，MOCK_MODE=true 时可以先不填

cd ..
pytest   # 跑 backend/tests 和 mcp_servers/tests
```

其余部分（Agent Harness、鉴权、API、前端、部署）会在后续阶段陆续补上对应的运行说明。
