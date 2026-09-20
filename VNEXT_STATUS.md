# vNext 实现状态

逐项对照求职档案 `PROJECT_DOSSIER.md` 第 11 节候选架构与第 12 节验证清单。只有代码 + 测试都落地才标"已实现"；只有设计没有代码的一律"未开始"。

最后更新：2026-09-20

**环境**：本机系统 Python 只有 3.9，另外用 `~/miniconda3` 建了一个独立的 `mcp-agent-vnext` conda 环境（Python 3.11.16），`backend/requirements.txt` 已在其中装好，`pytest`（42 个用例）已在这个环境里跑绿；下面标"已实现"的都是在这个环境里真正跑通的结果，不是代码走查。激活方式：`source ~/miniconda3/bin/activate mcp-agent-vnext`。

| 模块 | 对应档案位置 | 状态 | 代码位置 | 测试/验证 |
| --- | --- | --- | --- | --- |
| 仓库脚手架 | - | 已完成 | 根目录 | - |
| MCP Tool Gateway / Registry（allowlist、命名去冲突、schema 校验） | §11 | 已实现 | `backend/app/mcp_gateway/registry.py` | 真实启动 weather/write 两个 stdio 子进程，`discover_all()` 跑通，`get_tools(server_name=...)` 走的是主路径（非降级分支） |
| 超时 / 重试 / 熔断器 | §11 | 已实现 | `backend/app/mcp_gateway/client.py`, `circuit_breaker.py` | `backend/tests/test_circuit_breaker.py`（4 用例）pytest 跑绿；重试/超时的真实故障场景（比如真的把某个 server 打挂）还没做专门的故障注入测试 |
| 健康检查 / 单 Server 故障隔离 | §11, §10.2 | 已实现 | `backend/app/mcp_gateway/health.py`, `/readyz` | 真实起服务验证过：`map` server 没起来时，`/readyz` 里只有 `map` 被标 `unhealthy`，`weather`/`write` 仍然 `healthy` 且可以正常调用——单 server 故障没有把整个工具列表清空，这正是要修的那个具体缺陷 |
| 幂等键（写类工具去重） | §11, §12.8 | 已实现 | `backend/app/mcp_gateway/idempotency.py` | `backend/tests/test_idempotency.py`（3 用例）pytest 跑绿；过程中发现并修复了一个真 bug（aiosqlite 连接被 await 两次导致 "threads can only be started once"）；另外用真实 GatewayClient 调用 `write.write_file` 两次同一个 idempotency_key，确认第二次是 `idempotent_replay: true`、没有真的重写文件 |
| Weather Server 重写（重试/缓存/结构化错误） | §7, §10.4 | 进行中 | `mcp_servers/weather_server.py` | 真实子进程启动、`get_weather_tips` 端到端调通；`query_weather` 因为没有 OPENWEATHER_API_KEY，只验证了"未配置 key 时返回结构化 provider 错误"这条路径，重试/缓存逻辑本身未触发验证 |
| Write Server 重写（路径沙箱、并发防覆盖、幂等） | §7, §12.8 | 已实现 | `mcp_servers/write_server.py` | `mcp_servers/tests/test_write_server.py`（6 用例）pytest 跑绿；额外用真实 GatewayClient 端到端验证了"未确认拒绝写入→确认后写入→重复调用走幂等回放" |
| 地图 MCP Server（免 Key，替换占位符） | §7, §12.3 | 未开始 | `mcp_servers/map_server.py` | 代码完成，但还没真的用 `streamable-http` transport 起过这个 Server 或连过 Nominatim，`mcp.run(transport="streamable-http")` 的参数仍未验证 |
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
| Vue3 前端（真实 thread_id、SSE 消费、语法高亮、分级错误+重试、HITL 确认卡） | §9 偏差 5-6, §11 | 未开始 | `frontend/src/` | - |
| Playwright E2E | §12.9 | 未开始 | `frontend/e2e/` | - |
| Docker Compose 本地部署 | §11 | 未开始 | `ops/docker-compose.yml` | - |

## 说明

- "状态"只有三档：未开始 / 进行中 / 已实现（代码+测试）。不写"已设计"，避免和档案里"候选设计 ≠ 已实现"的区分混淆。
- 本文件不会跨仓库修改求职档案 `PROJECT_DOSSIER.md`；更新那份档案是用户自己的后续任务，这里只提供可引用的证据清单。

## 开发过程中发现的真问题（面试可以直接讲的坑）

- **MCP stdio 子进程不会继承父进程完整环境变量**：`mcp` SDK 的 `stdio_client` 在没有显式传 `env` 时，用的是一份精简的 `get_default_environment()`，不是 `os.environ` 的完整拷贝。一开始指望父进程 `os.environ["WRITE_WORKSPACE_DIR"]` 能被子进程读到，测试直接证伪了（文件写到了默认位置而不是测试期望的临时目录）。修复：`server_specs.py` 里显式给每个 stdio server 声明要转发的变量白名单（`_forward_env()`），而不是指望"反正是同一台机器"。这本身也是更安全的默认行为——本地子进程不会平白拿到一堆和它无关的密钥。
- **aiosqlite 连接不能 await 两次**：见上面幂等键那一行，`async with await conn` 和显式 `await aiosqlite.connect()` 叠在一起会让后台线程启动两次直接报错。
- **`passlib` 和新版 `bcrypt` 不兼容**：`passlib` 已经停止维护，装了新版 `bcrypt`（它自己去掉了 `__about__` 之类的旧属性）以后，`passlib` 内部一个版本探测的自检会跑错，进而在 `hash()` 阶段抛出一个和实际密码长度完全无关的假错误（"password cannot be longer than 72 bytes"，哪怕密码只有 10 个字符）。换成直接用 `bcrypt` 库本身（`hash_password`/`verify_password`），不经过 `passlib` 这层。
- **`SessionManager` 的并发锁是单进程内的**：`asyncio.Lock` 只能防止同一个 Python 进程里的并发请求踩踏同一个 thread_id；多 worker/多副本部署下每个进程会有自己的一份锁，起不到跨进程互斥的作用。真要多 worker 部署，需要换成数据库行锁或 Redis 分布式锁——目前 VNEXT_STATUS 如实标注这个边界，没有假装已经解决。
- **SQLite 不会自动建父目录**：`DATABASE_URL=sqlite+aiosqlite:///./data/app.db` 指向的 `data/` 目录如果不存在，`sqlite3.connect()` 直接报 "unable to open database file"，错误信息完全看不出是目录问题。pytest 里一直没暴露，因为测试用的要么是 `:memory:`，要么是 `tmp_path`（pytest 自己会建好这个目录）；直到真的用 `uvicorn` 起服务器才踩到。修复：`db/engine.py` 的 `make_engine()` 现在会自己解析 URL、提前 `mkdir(parents=True, exist_ok=True)`。这也是为什么"pytest 全绿"不能替代"真的跑一次服务器"——集成测试用的临时目录会悄悄掩盖这类问题。
- **必须真起一次服务器才能验证的东西，pytest 集成测试测不出来**：上面这条 bug 就是例子。这一轮之后确认过一次：`uvicorn app.main:app` 真实起进程、真实用 `curl` 走完注册→登录→建会话→聊天→HITL 确认→读到真实写入的文件这一整条链路，才敢把"FastAPI SSE /chat"这一行标成"已实现"。
