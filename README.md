# MCP Multi-Tool Agent

![python](https://img.shields.io/badge/python-3.11-3776AB) ![vue](https://img.shields.io/badge/frontend-vue3-42b883) ![langgraph](https://img.shields.io/badge/orchestration-langgraph-1C3C3C) [![CI](https://github.com/z8ri/mcp-multi-tool-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/z8ri/mcp-multi-tool-agent/actions/workflows/ci.yml) [![license](https://img.shields.io/badge/license-MIT-3DA639)](LICENSE)

一个从零手写的 LangGraph 状态图（`agent` / `tools` / `confirm` / `finalize` 四个节点 + 条件边），前面接一个带熔断器、健康检查、幂等键、超时重试的 MCP Tool Gateway，支持多用户会话隔离、可从进程重启中恢复的对话状态，以及写文件这类有副作用操作的人工确认——HITL 通过 LangGraph 的 `interrupt()` 实现，图会在 `confirm` 节点暂停执行，等待一次 API 调用批准或拒绝后再继续。72 个自动化测试，`backend/app` 行覆盖率 94%，CI 在每次 push 上运行；该链路已用 Qwen API 完成端到端联调，细节见 [docs/ENGINEERING_NOTES.md](docs/ENGINEERING_NOTES.md)。

## 工作原理

```mermaid
flowchart LR
    UI["Vue3 前端<br/>JWT 登录 + SSE 消费 + HITL 确认卡"] --> API["FastAPI /chat (SSE)<br/>JWT 鉴权 · 限流 · CORS 白名单"]
    API --> SM["SessionManager<br/>user → conversation → thread<br/>同 thread 并发锁"]
    SM --> G["LangGraph 状态图<br/>agent → tools → confirm(HITL) → finalize"]
    G -.持久化.-> CK[(SQLite<br/>Checkpointer)]
    G --> GW["MCP Tool Gateway<br/>熔断器 · 幂等键 · 超时重试 · 健康检查"]
    GW --> W["weather MCP<br/>stdio"]
    GW --> WR["write MCP<br/>stdio，有副作用"]
    GW --> M["map MCP<br/>Streamable HTTP"]
    G -.span.-> TR[(Trace)]
    API -.token/cost.-> BG[(Budget)]
    API -.failure.-> BC[(Bad Case)]
```

`thread_id` 全程只存在于服务端（`SessionManager` 维护 `conversation_id → thread_id` 的映射），前端只知道 `conversation_id`，拿不到也改不了 LangGraph 的 thread 标识。写文件这类有副作用的工具调用会让图在 `confirm` 节点真正 `interrupt()`，客户端提交 `confirm: true/false` 之后才 `resume`——中间如果进程重启，SQLite Checkpointer 能把暂停状态原样恢复。

## 关键设计决策

按 ADR 的方式记录几个不是唯一解、但各自有明确取舍的决定；完整列表和验证过程见 [docs/ENGINEERING_NOTES.md](docs/ENGINEERING_NOTES.md)。

**HITL 用 LangGraph 的 `interrupt()` 实现，而不是一个应用层的"待确认"状态字段。**
图在 `confirm` 节点真正暂停，写文件工具在客户端提交 `confirm: true` 之前不会被调用；暂停状态随 SQLite Checkpointer 持久化，进程重启不丢。代价：写类工具的调用路径比纯 ReAct 循环多一次显式的图状态转移，暂停/批准/拒绝三条路径都需要单独覆盖。

**每个 MCP Server 独立熔断，Gateway 不作为单一故障域。**
一个 Server 的健康状态只影响它自己的工具列表，`/readyz` 按 Server 分别汇报。代价：`/readyz` 的语义从"整体健康"变成"逐 Server 健康"，调用方要按这个语义读，不能简单取一个布尔值。

**幂等键由调用方提供并复用，Gateway 不代为生成。**
调用方对同一操作复用同一个 key 时，第二次调用直接拿回第一次的结果，不重放副作用。代价：正确性依赖调用方遵守"同一意图用同一个 key"的约定，Gateway 本身判断不出两次调用是否代表同一件事。

**成本预算在调用模型之前拦截，而不是记账后再报警。**
累计花费超过阈值时，请求在真正触达模型之前就被 402 拒绝。代价：价格表是手工维护的近似值而非实时计费 API，`GET /budget` 里显式带了 `price_table_as_of` 字段，不隐藏这个事实。

**SessionManager 的并发控制用进程内 `asyncio.Lock`，不引入分布式锁。**
单 worker 部署下足够正确，也不用为此引入 Redis 依赖。代价：多 worker/多副本部署下每个进程有自己的锁，起不到跨进程互斥的作用——这是已知边界，见下方。

## 模块

- **Agent Harness**（`backend/app/agent/`）——自定义 LangGraph 状态图 + SQLite Checkpointer，2 个端到端用例覆盖暂停/批准/拒绝三条路径
- **MCP Tool Gateway**（`backend/app/mcp_gateway/`）——allowlist、超时重试、熔断器、健康检查、幂等键，4 + 4 个用例，另有故障隔离验证
- **MCP Server**（`mcp_servers/`）——weather（重试/缓存/结构化错误）、write（路径沙箱/并发防覆盖）、map（免 Key，Streamable HTTP），7 + 6 个用例，Docker 部署中验证过
- **鉴权与会话**（`backend/app/auth/`, `backend/app/sessions/`）——JWT + SessionManager，10 + 5 个用例，含 `asyncio.gather` 并发场景验证
- **API 层**（`backend/app/api/`）——SSE `/chat`、`error{code, retryable}` 分级错误、限流、日志脱敏，7 + 5 个用例
- **可观测性**（`backend/app/trace/`, `budget/`, `badcases/`）——结构化 Trace、按用户成本预算、Bad Case 收集，2 + 6 + 4 个用例
- **前端**（`frontend/src/`）——`conversation_id` 隔离、SSE 消费、HITL 确认卡、分级错误+重试，Playwright 4 个用例

72 个用例、`backend/app` 行覆盖率 94%，CI 每次 push 运行（[Actions](https://github.com/z8ri/mcp-multi-tool-agent/actions)）；Docker Compose 和生产 Qwen API 均已完成端到端联调。

## 已知边界

如实列几条明确知道、但这一版没有解决的问题，而不是含糊带过：

- **多 worker/多副本部署**：`SessionManager` 的并发锁是进程内的，跨进程无效，需要换成数据库行锁或分布式锁。
- **前端会话历史回放**：切换到一个已有对话时，界面不会从后端重新拉取历史消息，只在当前页面会话内靠 SSE 事件累积；服务端状态本身没有丢。
- **`/bad-cases` 与 `/budget` 的访问控制**：目前任何登录用户都能看，没有角色系统收窄成运维视角。

## 目录结构

```
backend/        FastAPI 应用、Agent Harness、MCP Gateway、鉴权、数据库模型
mcp_servers/    独立的 MCP Server 进程（weather / write / map）
frontend/       Vue3 前端
ops/            Docker Compose 与部署配置
docs/           实现状态、工程笔记
```

## 环境要求

- **Python 3.11+**（`mcp`、`langgraph-checkpoint-sqlite` 等依赖要求 3.10+）。
- **Node.js 18+**。

## 快速开始

```bash
conda create -n mcp-agent python=3.11
conda activate mcp-agent

pip install -r backend/requirements.txt
cp .env.example .env   # MOCK_MODE=true（默认值）时不需要填任何 Key

pytest   # 跑 backend/tests 和 mcp_servers/tests
```

`pytest.ini` 接了 `pytest-cov`，每次跑 `pytest` 都会带一份 `backend/app` 的行覆盖率报告；目前是 72 个用例、94% 行覆盖率（`mcp_servers/*` 是独立子进程，跨进程边界 coverage.py 量不到，不算在这个数字里）。

### 持续集成

`.github/workflows/ci.yml` 会在 push/PR 时跑一遍后端 `pytest`（含上面那份覆盖率报告）、Alembic 基线迁移的 upgrade/downgrade、前端 `vue-tsc` 类型检查 + `vite build`——都不需要真实 API Key，结果见仓库的 [Actions 页面](https://github.com/z8ri/mcp-multi-tool-agent/actions)。

### 起后端、用 mock 模式试一遍完整链路（不需要任何 API Key）

```bash
cd backend
uvicorn app.main:app --reload
```

另开一个终端：

```bash
# 注册并拿到 token
TOKEN=$(curl -s -X POST localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"correct horse battery staple"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 建一个会话
CONV_ID=$(curl -s -X POST localhost:8000/conversations \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"demo"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 聊天（SSE），mock 模式下发"写"相关的话会触发写文件工具、需要走确认
curl -N -X POST localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"conversation_id\": $CONV_ID, \"message\": \"帮我写一个笔记\"}"

# 上面那次会在 confirm_required 事件处结束；批准执行：
curl -N -X POST localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"conversation_id\": $CONV_ID, \"confirm\": true}"
```

`MOCK_MODE=false` 并填好 `DASHSCOPE_API_KEY` 之后，同一套 API 会换成真实调用通义千问；天气/地图工具本身默认不需要额外 Key（地图走自建的 Nominatim Server，天气没配 `OPENWEATHER_API_KEY` 时会返回结构化的"未配置"错误而不是崩溃）。`QWEN_MODEL` 要填经典命名（默认值 `qwen-plus`）——阿里云百炼控制台"免费额度"页面里那些版本号式的模型名（比如 `qwen3.8-flash`）是给别的接口用的，直接填给这里会报 `400 InvalidParameter: url error`。该链路（Qwen 推理 + 工具调用 + HITL + 文件写入）已用生产 Key 验证，见 `docs/ENGINEERING_NOTES.md`。

### 查一次对话的 Trace

```bash
curl -s localhost:8000/conversations/$CONV_ID/trace -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### 查预算用量 / Bad Case

```bash
curl -s localhost:8000/budget -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s localhost:8000/bad-cases -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### 跑 Eval 回归套件

```bash
cd backend
python -m eval.runner
```

## 前端

后端起好之后（见上面），另开一个终端：

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL 指向后端，默认 http://localhost:8000
npm run dev
```

浏览器打开 `http://localhost:5173`，注册一个账号，新建对话，跟它说"今天天气怎么样"或者"帮我写一个笔记"就能看到工具调用、HITL 确认卡、分级错误+重试这些效果。详见 [frontend/README.md](frontend/README.md)；端到端测试见 [frontend/e2e/README.md](frontend/e2e/README.md)。

## Docker 部署

一键起全栈（`map-mcp` + `backend` + `frontend`，`backend` 内部再拉起 `weather`/`write` 两个 stdio 子进程）：

```bash
cp .env.example .env   # MOCK_MODE=true 不需要填任何 Key
docker compose -f ops/docker-compose.yml up --build
```

起来之后：前端 `http://localhost:5173`，后端 `http://localhost:8000`，地图 MCP Server（Streamable HTTP）`http://localhost:8811/mcp`。`backend` 会等 `map-mcp` 健康检查通过、`frontend` 会等 `backend` 健康检查通过才启动，验证的是"单 Server 故障不拖垮整体"这条在容器编排层面也成立。

`backend-data`/`backend-output` 是具名 volume，装的是 SQLite 数据库文件和 `write_file` 落盘的内容，`docker compose down` 不会删，`docker compose down -v` 才会。

`docker compose up -d --build` 已验证通过：三个容器按顺序变 healthy，`/readyz` 里 `map`/`weather`/`write` 三个工具都可用，`map.geocode` 返回了 Nominatim 的数据，前端也成功连接到容器内的后端。过程中修了两个只有在干净容器里从头构建才会暴露的问题：`mcp` 包在两个镜像里解析出了不同的大版本、以及 map-mcp 的健康检查一开始把 Streamable HTTP 端点对 406 的正常响应误判成"挂了"——都已经修好，细节见 `docs/ENGINEERING_NOTES.md`。

## 数据库 Schema 迁移

业务库（`User`/`Conversation`，`backend/app/db/models.py`）用 [Alembic](https://alembic.sqlalchemy.org/) 管理版本化迁移，起服务时仍然是 `SQLModel.metadata.create_all()`（图快，见 `db/engine.py` 的 `init_db()`），但**改已有表结构**（加字段、改约束）应该走 Alembic，而不是直接改 `models.py` 指望 `create_all` 把已有数据库也改对——`create_all` 只会建"不存在的表"，不会给已有表加新列。

```bash
cd backend
python -m alembic upgrade head       # 应用所有迁移到 DATABASE_URL 指向的库
python -m alembic revision --autogenerate -m "描述这次改了什么"   # 改完 models.py 后生成新迁移
```

**范围边界**：`idempotency_keys`/`trace_spans`/`budget_usage`/`bad_cases` 这几张表不归 Alembic 管——它们各自是独立 SQLite 文件里的单表日志/缓存，用裸 `CREATE TABLE IF NOT EXISTS` 建表，只增不改列，这个机制本身就够用；接进 Alembic 反而是过度设计。

## 数据保留

`trace_spans` 每次模型/工具调用都落一条，长期跑会无限增长；`idempotency_keys` 有 TTL 但原来是懒惰过期（没人查的过期 key 会一直留着）；`bad_cases` 里已经标记"已处理"的旧记录也没有清理机制。现在服务**每次启动时**会主动清一次：过期的幂等键、超过 `TRACE_RETENTION_DAYS`（默认 30 天）的 trace span、已处理超过 30 天的 bad case。没有引入额外的定时任务框架——这个粒度对这个项目的规模够用，真要 7x24 常驻部署应该换成独立的定时任务，而不是"重启时才清一次"。

## License

[MIT](LICENSE)
