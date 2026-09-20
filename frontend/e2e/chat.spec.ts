import { test, expect } from '@playwright/test'

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 10000)}@example.com`
}

async function registerAndEnterChat(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByText('还没有账号？去注册').click()
  await page.getByTestId('email-input').fill(uniqueEmail())
  await page.getByTestId('password-input').fill('correct horse battery staple')
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('new-conversation')).toBeVisible()
}

test('register, chat about weather, no confirmation needed', async ({ page }) => {
  await registerAndEnterChat(page)
  await page.getByTestId('new-conversation').click()

  await page.getByTestId('message-input').fill('今天天气怎么样')
  await page.getByTestId('send-button').click()

  await expect(page.getByTestId('tool-call')).toContainText('weather.get_weather_tips')
  await expect(page.getByTestId('tool-result')).toContainText('执行成功')
  await expect(page.getByTestId('confirm-card')).toHaveCount(0)
})

test('write request pauses for confirmation, approving actually executes it', async ({ page }) => {
  await registerAndEnterChat(page)
  await page.getByTestId('new-conversation').click()

  await page.getByTestId('message-input').fill('帮我写一个笔记')
  await page.getByTestId('send-button').click()

  await expect(page.getByTestId('confirm-card')).toBeVisible()
  await expect(page.getByTestId('message-input')).toBeDisabled() // 等确认时不能接着发消息

  await page.getByTestId('confirm-approve').click()

  await expect(page.getByTestId('confirm-card')).toHaveCount(0)
  await expect(page.getByTestId('tool-result')).toContainText('执行成功')
  await expect(page.getByTestId('message-input')).toBeEnabled()
})

test('rejecting the confirmation does not execute the write', async ({ page }) => {
  await registerAndEnterChat(page)
  await page.getByTestId('new-conversation').click()

  await page.getByTestId('message-input').fill('帮我写一个笔记')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('confirm-card')).toBeVisible()

  await page.getByTestId('confirm-reject').click()

  await expect(page.getByTestId('confirm-card')).toHaveCount(0)
  await expect(page.getByTestId('tool-result')).toContainText('用户拒绝执行该操作')
})

test('wrong password on login shows a dismissible, non-retryable error', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('email-input').fill('nobody-registered-with-this-email@example.com')
  await page.getByTestId('password-input').fill('whatever-password')
  await page.getByTestId('submit-button').click()

  const banner = page.locator('.error-banner')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('身份验证失败')
  await expect(banner).toContainText('邮箱或密码错误')
  await expect(banner.getByText('重试')).toHaveCount(0) // 密码错了不是"重试"能解决的，不该给重试按钮
})
