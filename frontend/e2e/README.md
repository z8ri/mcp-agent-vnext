# Playwright E2E

这些用例跑在真实的前端 + 真实的后端（`MOCK_MODE=true`，不需要任何 API Key）上，
不是纯前端的组件测试——用例本身就是照着手工验证过的那条链路写的：注册 → 建会话 →
发消息 → 看到 `tool_call`/`tool_result`/`confirm_required` → 批准/拒绝 → 看到最终结果。

## 跑之前

Playwright 只管前端 dev server（配置见 `playwright.config.ts`），**后端要自己先起好**：

```bash
# 另一个终端
source ~/miniconda3/bin/activate mcp-agent-vnext   # 或者你自己的 Python 3.11+ 环境
cd backend
cp ../.env.example ../.env   # MOCK_MODE=true，不需要填 Key
uvicorn app.main:app --port 8000
```

## 跑

```bash
cd frontend
npx playwright install chromium   # 第一次跑之前装一次浏览器
npx playwright test
```

## 为什么不让 Playwright 也顺手把后端起了

后端需要 Python 3.11+（这台开发机的系统 Python 是 3.9，用 conda 单独建的环境），
把一条"激活某个 conda 环境"的命令写死在 `playwright.config.ts` 里，换一台机器跑
基本就是错的。让后端启动方式保持和日常开发、以及 Stage H 的 docker-compose 编排
一致，比在测试配置里硬编码一条本机专属命令更值得信任。
