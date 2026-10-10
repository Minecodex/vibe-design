import { test, expect } from '@playwright/test'

for (const theme of ['light', 'dark']) {
  test(`real login and project persistence in ${theme}`, async ({ page }) => {
    await page.addInitScript((selectedTheme) => {
      localStorage.setItem('i18nextLng', 'zh-CN')
      localStorage.setItem('global-storage-v2', JSON.stringify({ state: { theme: selectedTheme }, version: 0 }))
    }, theme)
    await page.goto('/dashboard/projects')
    await expect(page.getByPlaceholder('请输入用户名或邮箱')).toBeVisible()
    await page.getByPlaceholder('请输入用户名或邮箱').fill('ciadmin')
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('CI-public-fixture-123!')
    await page.locator('button[type="submit"]').click()
    await expect(page).toHaveURL(/\/dashboard\/projects/)
    await page.getByRole('button', { name: '新建项目', exact: true }).click()
    await expect(page).toHaveURL(/\/canvas\/\d+/)
    const projectId = page.url().match(/\/canvas\/(\d+)/)?.[1]
    expect(projectId).toBeTruthy()
    const reloadResponse = page.waitForResponse(response =>
      response.request().method() === 'GET' && response.url().endsWith(`/api/v1/projects/${projectId}`)
    )
    await page.reload()
    await expect(page).toHaveURL(new RegExp(`/canvas/${projectId}$`))
    const loaded = await reloadResponse
    // The visible reload remains the primary browser assertion; the same
    // real API response must also identify the newly persisted project.
    expect(loaded.ok()).toBeTruthy()
    const record = await loaded.json()
    expect(String(record.data.id)).toBe(projectId)
    await page.goto('/dashboard/projects')
    await expect(page.getByPlaceholder('搜索项目...')).toBeVisible()
  })
}
