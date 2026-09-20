# MCP Agent vNext

基于 MCP 多服务 + LangGraph 自定义图 + FastAPI + Vue3 的多工具 ReAct Agent，独立实现（JHU 2026 春季个人课程作业）。

这是对某求职机构提供的教学参考代码（`weather`/`write` 两个本地 MCP Server + LangGraph 预构建 ReAct Agent + Vue 单页聊天界面）的独立重写和扩展，目标是把参考代码中的教学简化点，实现为真正可运行、可验证的完整系统：

- 自定义 LangGraph 状态图（而不是预构建 `create_react_agent`），显式区分 agent / tools / confirm(HITL) / finalize 节点，写文件这类有副作用的操作会让图真的暂停等人确认
- MCP Tool Gateway：allowlist、超时、重试、熔断、健康检查、幂等键、单 Server 故障隔离
- 真实多用户会话隔离：JWT 登录 + SessionManager（user → conversation → LangGraph thread）+ 同 thread 并发锁，前端永远看不到、也改不了 `thread_id`
- SQLite Checkpointer（跨重启恢复），而不是进程内 `InMemorySaver`
- SSE 按图的执行步骤增量推送（工具调用、确认请求、工具结果、最终消息），不是等全部跑完才一次性返回一个 JSON；逐 token 的模型级流式还没有用真实 Key 验证过，见 `VNEXT_STATUS.md`
- `MOCK_MODE=true` 时用关键词触发的假模型驱动真实的 MCP Gateway/Server，不需要任何 API Key 就能把整条链路（注册登录 → 建会话 → 聊天 → 工具调用 → HITL 确认 → 写文件）跑通
- 自建免 Key 地图 MCP Server（基于 OpenStreetMap Nominatim），替换参考代码中的占位符地图配置
- 结构化 Trace：每次模型调用、每次工具调用都落一条 span（耗时、成功/失败），`GET /conversations/{id}/trace` 能按时间顺序查一次对话的完整轨迹
- Eval 回归套件（`backend/eval/`）：5 个脚本化场景（天气成功、写文件确认执行、写文件拒绝不执行、无关消息不触发工具、单 server 故障不影响其它工具），`MOCK_MODE` 下不需要任何 Key 就能跑，`python -m eval.runner` 单独跑出报告，也接进了 `pytest`

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

- **Python 3.11+**（`mcp`、`langgraph-checkpoint-sqlite` 等依赖要求 3.10+）。本机系统自带的是 Python 3.9，开发时用 conda 单独建了一个 3.11 环境，见下面的快速开始。
- **Node.js 18+**（开发用的是 Homebrew 装的 `node@26`）。

## 快速开始

用 conda（本仓库开发时用的方式，系统 Python 版本不够时的推荐做法；系统 Python 本身就是 3.11+ 的话用标准 venv 也一样）：

```bash
conda create -n mcp-agent-vnext python=3.11
conda activate mcp-agent-vnext

pip install -r backend/requirements.txt
cp .env.example .env   # MOCK_MODE=true（默认值）时不需要填任何 Key

pytest   # 跑 backend/tests 和 mcp_servers/tests，本仓库在这个环境下已跑绿
```

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

`MOCK_MODE=false` 并填好 `DASHSCOPE_API_KEY` 之后，同一套 API 会换成真实调用通义千问；天气/地图工具本身默认不需要额外 Key（地图走自建的 Nominatim Server，天气没配 `OPENWEATHER_API_KEY` 时会返回结构化的"未配置"错误而不是崩溃）。

### 查一次对话的 Trace

```bash
curl -s localhost:8000/conversations/$CONV_ID/trace -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
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

起来之后：前端 `http://localhost:5173`，后端 `http://localhost:8000`，地图 MCP Server（Streamable HTTP）`http://localhost:8811/mcp`。`backend` 会等 `map-mcp` 健康检查通过、`frontend` 会等 `backend` 健康检查通过才启动，验证的是档案里"单 Server 故障不拖垮整体"这条能不能在容器编排层面也成立。

`backend-data`/`backend-output` 是具名 volume，装的是 SQLite 数据库文件和 `write_file` 落盘的内容，`docker compose down` 不会删，`docker compose down -v` 才会。

`docker compose up -d --build` 已经真实跑通过：三个容器按顺序变 healthy，`/readyz` 里 `map`/`weather`/`write` 三个工具都可用，`map.geocode` 真的查到了 Nominatim 的数据，浏览器打开前端也真的连上了容器里的后端。过程中修了两个只有在干净容器里从头构建才会暴露的问题：`mcp` 包在两个镜像里解析出了不同的大版本（要锁 `mcp<2`），以及 map-mcp 的健康检查一开始把 Streamable HTTP 端点对 406 的正常响应误判成"挂了"——都已经修好，细节见 `VNEXT_STATUS.md`。
