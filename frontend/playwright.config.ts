import { defineConfig, devices } from '@playwright/test'

/**
 * 只让 Playwright 管前端 dev server；后端（FastAPI，MOCK_MODE=true）需要
 * 提前在另一个终端起好，见 frontend/e2e/README.md。
 * 原因：后端要跑在装了 Python 3.11+ 依赖的环境里，写死一条激活 conda 环境的命令
 * 到这份配置里对换一台机器跑就是错的——不如让后端启动方式保持和平时开发、
 * 以及 docker-compose 编排一致，Playwright 只管它自己那一半。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false, // 用例之间会创建/复用账号状态，先不并行，避免互相干扰
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev -- --port 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
})
