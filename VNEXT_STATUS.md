# vNext 实现状态

逐项对照求职档案 `PROJECT_DOSSIER.md` 第 11 节候选架构与第 12 节验证清单。只有代码 + 测试都落地才标"已实现"；只有设计没有代码的一律"未开始"。

最后更新：2026-09-20

**总览**：下表 21 行里，18 行"已实现"（代码 + 真实测试/手工验证都有），3 行"进行中"（代码写了，但有具体没验证到的点——都写清楚了差在哪），0 行"未开始"。3 行"进行中"分别是：Weather Server 的 `query_weather`（缺 OPENWEATHER_API_KEY）、流式索引错误的根因复现（缺 DASHSCOPE_API_KEY）、限流/日志脱敏的专项测试（代码在，没写"触发 429"和"脱敏接入实际请求日志"的测试）。下面"下一步"列出了这些和其它值得继续做的事。

**环境**：本机系统 Python 只有 3.9，另外用 `~/miniconda3` 建了一个独立的 `mcp-agent-vnext` conda 环境（Python 3.11.16），`backend/requirements.txt` 已在其中装好，`pytest`（42 个用例）已在这个环境里跑绿；下面标"已实现"的都是在这个环境里真正跑通的结果，不是代码走查。激活方式：`source ~/miniconda3/bin/activate mcp-agent-vnext`。本机原本也没有 Node.js，用 Homebrew 装了 `node@26`；也没装 Docker，装好 Docker Desktop 后引擎一度起不来（Rosetta 安装失败），排查和修复过程见下面"真问题"部分，现在 `docker compose up` 已经真实跑通。

| 模块 | 对应档案位置 | 状态 | 代码位置 | 测试/验证 |
| --- | --- | --- | --- | --- |
| 仓库脚手架 | - | 已完成 | 根目录 | - |
| MCP Tool Gateway / Registry（allowlist、命名去冲突、schema 校验） | §11 | 已实现 | `backend/app/mcp_gateway/registry.py` | 真实启动 weather/write 两个 stdio 子进程，`discover_all()` 跑通，`get_tools(server_name=...)` 走的是主路径（非降级分支） |
| 超时 / 重试 / 熔断器 | §11 | 已实现 | `backend/app/mcp_gateway/client.py`, `circuit_breaker.py` | `backend/tests/test_circuit_breaker.py`（4 用例）pytest 跑绿；重试/超时的真实故障场景（比如真的把某个 server 打挂）还没做专门的故障注入测试 |
| 健康检查 / 单 Server 故障隔离 | §11, §10.2 | 已实现 | `backend/app/mcp_gateway/health.py`, `/readyz` | 真实起服务验证过：`map` server 没起来时，`/readyz` 里只有 `map` 被标 `unhealthy`，`weather`/`write` 仍然 `healthy` 且可以正常调用——单 server 故障没有把整个工具列表清空，这正是要修的那个具体缺陷 |
| 幂等键（写类工具去重） | §11, §12.8 | 已实现 | `backend/app/mcp_gateway/idempotency.py` | `backend/tests/test_idempotency.py`（3 用例）pytest 跑绿；过程中发现并修复了一个真 bug（aiosqlite 连接被 await 两次导致 "threads can only be started once"）；另外用真实 GatewayClient 调用 `write.write_file` 两次同一个 idempotency_key，确认第二次是 `idempotent_replay: true`、没有真的重写文件 |
| Weather Server 重写（重试/缓存/结构化错误） | §7, §10.4 | 进行中 | `mcp_servers/weather_server.py` | 真实子进程启动、`get_weather_tips` 端到端调通；`query_weather` 因为没有 OPENWEATHER_API_KEY，只验证了"未配置 key 时返回结构化 provider 错误"这条路径，重试/缓存逻辑本身未触发验证 |
| Write Server 重写（路径沙箱、并发防覆盖、幂等） | §7, §12.8 | 已实现 | `mcp_servers/write_server.py` | `mcp_servers/tests/test_write_server.py`（6 用例）pytest 跑绿；额外用真实 GatewayClient 端到端验证了"未确认拒绝写入→确认后写入→重复调用走幂等回放" |
| 地图 MCP Server（免 Key，替换占位符） | §7, §12.3 | 已实现 | `mcp_servers/map_server.py` | Docker 里真实用 `streamable-http` transport 起来了，`/readyz` 显示 `map` 健康、`map.geocode`/`map.reverse_geocode` 可用；直接调用 `geocode({"query": "Eiffel Tower"})` 拿到真实 Nominatim 结果（`48.8582599, 2.2945006`）——这是本项目第一次真正验证这个 Server，之前一直因为没跑过而标"未开始" |
| 自定义 LangGraph 图（agent/tools/confirm/finalize 节点与条件边） | §9 偏差 1, §11 | 已实现 | `backend/app/agent/graph.py`, `nodes.py`, `state.py` | `backend/tests/test_agent_graph.py`（2 用例）pytest 跑绿，用脚本化的 `FakeMessagesListChatModel` + 真实 weather/write 子进程做端到端验证：单 tool_call 走 HITL 暂停→批准→真的写文件；多 tool_call 批次里前面无副作用的先执行、遇到有副作用的暂停、拒绝后确实没有写文件 |
| SQLite Checkpointer（替换 InMemorySaver） | §10.1 | 已实现 | `backend/app/agent/checkpointer.py` | 同上两个测试都依赖它跨越两次 `ainvoke` 调用恢复状态（`interrupt()` 暂停后重新 resume），验证了检查点真的持久化了状态，不是纯内存 |
| 流式修复（`astream_events` 正确处理增量片段） | §9 偏差 4 | 进行中 | `backend/app/agent/graph.py`, `graph.py` 里的 `build_default_agent_graph` | `agent_node` 用 `.ainvoke()`（而不是手动拼流式片段）调用模型，原则上比参考代码手动处理 chunk 更不容易踩 index 错误；但真正的 token 级 SSE 流式在 Stage E 做，且没有 DASHSCOPE_API_KEY，没法验证 Tongyi 真实的流式分片行为是否触发过档案提到的那个 bug——**这里不编造一个没验证过的"已复现并修复"结论**，如实标成进行中 |
| JWT 鉴权 + 用户表 | §11 | 已实现 | `backend/app/auth/`, `backend/app/db/models.py` | `backend/tests/test_auth.py`（6 用例，含错误密码/重复邮箱/过期 token/篡改 token）+ `backend/tests/test_auth_dependencies.py`（4 用例，跑了一个真实 FastAPI+httpx ASGI 请求验证 `get_current_user` 依赖链）全部 pytest 跑绿 |
| SessionManager（user→conversation→thread，同 thread 并发锁） | §10.1, §11 | 已实现 | `backend/app/sessions/manager.py` | `backend/tests/test_session_manager.py`（5 用例）pytest 跑绿：跨用户越权访问被拒绝、只能看到自己的 conversation 列表、同一 thread 的并发请求被 `asyncio.Lock` 严格串行化（用真实 `asyncio.gather` 竞争验证顺序，不是靠猜时序） |
| FastAPI SSE `/chat`、分级错误事件 | §11 | 已实现 | `backend/app/api/routes_chat.py`, `sse.py` | `backend/tests/test_app_integration.py`（5 用例）pytest 跑绿 + 真实 `uvicorn` 起服务用 `curl` 手工过了一遍完整链路：注册→登录→建会话→"帮我写一个笔记"→SSE 收到 `tool_call`/`confirm_required`/`final`→提交 `confirm:true`→SSE 收到 `tool_result`/`message`，`backend/output/` 下真的多了一个内容正确的 `.txt` 文件 |
| `/healthz` `/readyz` | §11 | 已实现 | `backend/app/api/routes_admin.py` | 同上，真实 curl 验证过两个端点，`/readyz` 能看到 per-server 健康状态和熔断器状态 |
| CORS 白名单 / 限流 / 日志脱敏 | §10.3 | 进行中 | `backend/app/security/rate_limit.py`, `redaction.py`, `main.py` 里的 CORSMiddleware | CORS 配置代码完成，走集成测试间接覆盖（没有专门测跨域请求本身）；限流已经作为真实依赖挂在 `/chat` 上，但**没有写"连续请求触发 429"的测试**，`TokenBucket` 本身的算法逻辑也没有单独单测，只是代码走查；日志脱敏单独用脚本验证过 `dashscope_api_key` 这类字段会被替换成 `***redacted***`，但还没接到 `main.py` 实际的请求日志里 |
| Trace（结构化 span） | §11 | 已实现 | `backend/app/trace/tracer.py`, `GET /conversations/{id}/trace` | `backend/tests/test_app_integration.py` 里两个新用例 pytest 跑绿：真实走一轮天气对话后，trace 里能查到 `agent.invoke`/`tool.call:weather.get_weather_tips` 两个 span，状态和耗时都对；跨用户访问别人会话的 trace 会被拒绝（404）。范围边界：span 只到"网关发起工具调用"这一层，MCP transport 内部（比如 stdio 子进程里具体卡在哪一步）没有单独的 span；也没有做跨进程的分布式 trace context 传播——这些在 tracer.py 的注释里写清楚了，不算已实现 |
| Eval 回归场景（mock 模式可跑） | §12 | 已实现 | `backend/eval/cases.py`, `runner.py`，`backend/tests/test_eval_cases.py` | 5 个脚本化场景（天气成功、写文件确认后执行、写文件拒绝后不执行、无关消息不触发工具、单 server 故障不影响其它工具）全部通过 `MockAgentModel` + 真实 MCP 子进程跑通，每个用例独立临时目录、互不干扰；接进了 pytest（`test_eval_cases.py`，5 用例跑绿），也能用 `python -m eval.runner` 单独跑出一份文本报告。额外做了一次"harness 自检"：故意写一个错误断言，确认 runner 真的会报 FAIL 而不是摆设 |
| Vue3 前端（真实 thread_id、SSE 消费、语法高亮、分级错误+重试、HITL 确认卡） | §9 偏差 5-6, §11 | 已实现 | `frontend/src/` | 用内置浏览器手工走了一遍完整流程：注册→建会话→问天气（看到 tool_call/tool_result、不需要确认）→要求写笔记（看到确认卡→批准→看到执行成功，磁盘上真的多了文件）→再写一次→拒绝（看到"用户拒绝执行该操作"，磁盘上没有多文件）→同一会话里多轮历史正确保留。`thread_id` 全程前端拿不到，只有 `conversation_id`。类型检查（`vue-tsc -b`）和生产构建（`vite build`）都过 |
| Playwright E2E | §12.9 | 已实现 | `frontend/e2e/chat.spec.ts` | 4 个用例真实跑通（装了 Chromium）：天气问答不触发确认、写文件确认后真执行、拒绝后不执行、密码错误显示不可重试的错误提示。Playwright 只管前端 dev server，后端需要单独起好（`frontend/e2e/README.md` 里写了原因和步骤）——没有为了"一键跑"把机器专属的 conda 路径硬编码进配置文件 |
| Docker Compose 本地部署 | §11 | 已实现 | `ops/docker-compose.yml`, `backend/Dockerfile`, `mcp_servers/Dockerfile`, `frontend/Dockerfile` | `docker compose up -d --build` 真实跑通，三个容器按 `depends_on`+healthcheck 顺序起来（`map-mcp` healthy → `backend` healthy → `frontend`）；容器化的后端跑通了注册→登录→建会话→聊天→工具调用全流程，浏览器打开 `localhost:5173` 真实连上了容器化后端并拿到之前 curl 建的会话。这台机器一开始没装 Docker、装完后引擎起不来，排查过程和修复见下面"真问题"部分 |

## 说明

- "状态"只有三档：未开始 / 进行中 / 已实现（代码+测试）。不写"已设计"，避免和档案里"候选设计 ≠ 已实现"的区分混淆。
- 本文件不会跨仓库修改求职档案 `PROJECT_DOSSIER.md`；更新那份档案是用户自己的后续任务，这里只提供可引用的证据清单。
- **前端已知范围边界**：切换/重新选中一个已有 conversation 时，界面上的消息时间线不会从后端拉历史重新渲染——它只在当前这次页面会话里，靠实时收到的 SSE 事件累积。服务端（LangGraph checkpoint）本身是有完整历史的，只是前端目前没有一个"拉取某个 conversation 历史消息"的接口和渲染逻辑去用它；刷新页面或切到另一个会话再切回来，之前的对话内容会从界面上消失（但数据没丢，重新发消息还是接着之前的状态走）。这不是这一阶段计划范围内的项，如实记在这里而不是含糊带过。

## 下一步

按价值排序，不是必须按顺序做：

1. **补真实 Key，跑一次真实联调**：`DASHSCOPE_API_KEY`（必需）、`OPENWEATHER_API_KEY`（可选）。这是把"MOCK_MODE 全链路通"升级成"真的用通义千问推理"的唯一剩余步骤，本仓库现在完全具备条件，只是缺 Key。
2. **流式索引错误**：有了 Qwen key 之后，`ChatTongyi(streaming=True)` 真实跑几轮多工具对话，看会不会复现档案里说的那个流式解析崩溃；如果复现，保留错误栈和最小复现场景，写成回归测试，再判断是不是需要额外处理（而不是像参考代码那样直接关闭流式）。
3. **限流与日志脱敏的专项测试**：`backend/tests/test_rate_limit.py`（连续请求触发 429、令牌桶恢复速率）+ 把 `redaction.py` 的处理器接到 `main.py` 实际的请求日志管线里并验证。
4. **前端会话历史回放**：加一个 `GET /conversations/{id}/messages`（从 LangGraph checkpoint 读历史），切换/重新打开会话时前端拉一次渲染，补上 VNEXT_STATUS 里记的那个已知缺口。
5. **故障注入测试**：真的把一个 MCP server 进程杀掉/让它超时，验证熔断器状态转移和重试退避在真实故障下的行为，而不是只靠单元测试里模拟的失败结果。
6. **多 worker 部署**：如果真要多进程部署，`SessionManager` 的 `asyncio.Lock` 需要换成数据库行锁或 Redis 分布式锁——现在明确标了这个边界，不是文档遗漏。

## 开发过程中发现的真问题（面试可以直接讲的坑）

- **MCP stdio 子进程不会继承父进程完整环境变量**：`mcp` SDK 的 `stdio_client` 在没有显式传 `env` 时，用的是一份精简的 `get_default_environment()`，不是 `os.environ` 的完整拷贝。一开始指望父进程 `os.environ["WRITE_WORKSPACE_DIR"]` 能被子进程读到，测试直接证伪了（文件写到了默认位置而不是测试期望的临时目录）。修复：`server_specs.py` 里显式给每个 stdio server 声明要转发的变量白名单（`_forward_env()`），而不是指望"反正是同一台机器"。这本身也是更安全的默认行为——本地子进程不会平白拿到一堆和它无关的密钥。
- **aiosqlite 连接不能 await 两次**：见上面幂等键那一行，`async with await conn` 和显式 `await aiosqlite.connect()` 叠在一起会让后台线程启动两次直接报错。
- **`passlib` 和新版 `bcrypt` 不兼容**：`passlib` 已经停止维护，装了新版 `bcrypt`（它自己去掉了 `__about__` 之类的旧属性）以后，`passlib` 内部一个版本探测的自检会跑错，进而在 `hash()` 阶段抛出一个和实际密码长度完全无关的假错误（"password cannot be longer than 72 bytes"，哪怕密码只有 10 个字符）。换成直接用 `bcrypt` 库本身（`hash_password`/`verify_password`），不经过 `passlib` 这层。
- **`SessionManager` 的并发锁是单进程内的**：`asyncio.Lock` 只能防止同一个 Python 进程里的并发请求踩踏同一个 thread_id；多 worker/多副本部署下每个进程会有自己的一份锁，起不到跨进程互斥的作用。真要多 worker 部署，需要换成数据库行锁或 Redis 分布式锁——目前 VNEXT_STATUS 如实标注这个边界，没有假装已经解决。
- **SQLite 不会自动建父目录**：`DATABASE_URL=sqlite+aiosqlite:///./data/app.db` 指向的 `data/` 目录如果不存在，`sqlite3.connect()` 直接报 "unable to open database file"，错误信息完全看不出是目录问题。pytest 里一直没暴露，因为测试用的要么是 `:memory:`，要么是 `tmp_path`（pytest 自己会建好这个目录）；直到真的用 `uvicorn` 起服务器才踩到。修复：`db/engine.py` 的 `make_engine()` 现在会自己解析 URL、提前 `mkdir(parents=True, exist_ok=True)`。这也是为什么"pytest 全绿"不能替代"真的跑一次服务器"——集成测试用的临时目录会悄悄掩盖这类问题。
- **必须真起一次服务器才能验证的东西，pytest 集成测试测不出来**：上面这条 bug 就是例子。这一轮之后确认过一次：`uvicorn app.main:app` 真实起进程、真实用 `curl` 走完注册→登录→建会话→聊天→HITL 确认→读到真实写入的文件这一整条链路，才敢把"FastAPI SSE /chat"这一行标成"已实现"。
- **这台机器一开始没装 Docker，装上之后引擎也起不来**：`brew install --cask docker` 第一次卡在一步需要终端交互输入密码的 `sudo`，用户自己在终端跑完；装完之后 Docker Desktop 的虚拟化引擎又卡在"Starting the Docker Engine..."一直连不上，日志里翻出根因是 `VZErrorDomain Code=1: Failed to install Rosetta`——Docker 自己内置的 Rosetta 安装器在这台机器上跑失败了。绕过的办法：直接用系统自带的 `softwareupdate --install-rosetta --agree-to-license` 把 Rosetta 装好（不走 Docker 那条坏掉的路径），再 `pkill` 掉卡死在空转的 `com.docker.backend` 残留进程、重新打开 Docker Desktop，虚拟机才正常拉起来。这个项目其实完全不需要 Rosetta——三个镜像（`python:3.11-slim`/`node:20-slim`/`nginx:alpine`）都原生支持 arm64，Rosetta 只在需要跑 x86_64 镜像时才用得上。
- **`mcp` 包 2.x 是破坏性变更，两个 Dockerfile 装出了不一样的大版本**：`backend/Dockerfile` 因为同时装了 `langchain-mcp-adapters`，被它间接约束在 `mcp==1.30.0`；但 `mcp_servers/Dockerfile`（map-mcp 的独立镜像）只写了裸的 `pip install mcp`，构建时刚好撞上 PyPI 上更新的 `mcp==2.2.0`，而 2.x 把 `FastMCP` 改名成了 `MCPServer`，`map_server.py` 一启动就 `ModuleNotFoundError`。修复：两边都显式锁 `mcp<2`。这类"没有 lockfile、两个镜像各自解析出不同版本"的问题，只有真的在干净的容器里从头构建才会暴露——本机 conda 环境里那份 `mcp` 是几周前装的，一直没感知到 PyPI 上已经出了新的大版本。
- **Streamable HTTP 的健康检查不能用"能不能拿到 2xx"来判断**：`map-mcp` 的 healthcheck 一开始是裸 `urllib.request.urlopen('http://localhost:8811/mcp')`，容器日志显示服务其实已经正常起来了，但健康检查一直失败——原因是 MCP 的 Streamable HTTP 端点对请求的 `Accept` header 有强制要求，不带正确 header 的裸 GET 会被协议层正确地返回 406，而 `urlopen` 对任何非 2xx 状态码都会抛 `HTTPError`。修复：健康检查显式 `except urllib.error.HTTPError: pass`——收到 HTTP 响应（哪怕是 406）就足够证明进程活着、在正常处理请求，不需要真的走完一次 MCP 握手。
