# MCP Multi-Tool Agent — 前端

Vue 3 + TypeScript + Vite：`thread_id` 全程只存在于服务端，前端只带 `conversation_id`；聊天流用 `fetch` + `ReadableStream` 消费 SSE（不是原生 `EventSource`，因为要带自定义鉴权 header）；支持语法高亮、分级错误 + 重试按钮、HITL 确认卡。

## 目录

```
src/api/            fetch 封装：鉴权、conversations、SSE 聊天流
src/composables/    useAuth（token 状态）、useChat（驱动一次 SSE 对话）
src/components/      ConfirmCard（HITL 确认卡）、ErrorBanner（分级错误+重试）、TimelineItem
src/views/           LoginView、ChatView
e2e/                 Playwright 端到端测试，见 e2e/README.md
```

## 本地开发

```bash
npm install
cp .env.example .env   # VITE_API_BASE_URL 指向后端，默认 http://localhost:8000
npm run dev
```

后端启动方式见仓库根目录 `README.md`。

## 类型检查 / 构建

```bash
npm run typecheck
npm run build
```

## E2E 测试

见 [e2e/README.md](e2e/README.md)。
