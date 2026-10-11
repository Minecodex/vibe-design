import { test, expect } from '@playwright/test'
import type { CanvasItem } from '../../src/api/endpoints/projects'

type CanvasRecord = {
  id: number
  canvas_revision: number
  canvas_data: Array<{ id: string; text?: string; type?: string }>
}

for (const theme of ['light', 'dark']) {
  test(`production canvas autosave and revision fencing in ${theme}`, async ({ page }) => {
    await page.addInitScript((selectedTheme) => {
      localStorage.setItem('i18nextLng', 'zh-CN')
      localStorage.setItem('global-storage-v2', JSON.stringify({ state: { theme: selectedTheme }, version: 0 }))
    }, theme)
    await page.goto('/dashboard/projects')
    await page.getByPlaceholder('请输入用户名或邮箱').fill('ciadmin')
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('CI-public-fixture-123!')
    const login = page.waitForResponse(response =>
      response.request().method() === 'POST' && response.url().endsWith('/api/v1/auth/login')
    )
    await page.locator('button[type="submit"]').click()
    const response = await login
    expect(response.ok()).toBeTruthy()
    const token = (await response.json() as { access_token: string }).access_token
    expect(typeof token).toBe('string')
    const headers = { Authorization: `Bearer ${token}` }

    const created = await page.request.post('/api/v1/projects', {
      headers, data: { title: `Release canvas ${theme} ${Date.now()}` },
    })
    expect(created.ok()).toBeTruthy()
    const project = await created.json() as CanvasRecord
    const original = `Release canvas text ${theme}`
    const item: CanvasItem = { id: 'release-text', type: 'text', url: '', x: 240, y: 180, width: 320, height: 80, text: original }
    const seeded = await page.request.put(`/api/v1/projects/${project.id}`, {
      headers, data: { canvas_base_revision: project.canvas_revision, canvas_data: [item] },
    })
    expect(seeded.ok()).toBeTruthy()
    const initial = await seeded.json() as CanvasRecord

    await page.goto(`/canvas/${project.id}`)
    await expect(page.getByTitle(original, { exact: true })).toBeVisible()
    await page.getByTitle(original, { exact: true }).dblclick()
    const editor = page.getByTitle(original, { exact: true })
    await expect(editor).toHaveJSProperty('tagName', 'TEXTAREA')
    await expect(editor).toHaveValue(original)
    const updated = `Persisted production canvas ${theme}`
    await editor.fill(updated)
    const saved = page.waitForResponse(candidate => {
      if (candidate.request().method() !== 'PUT' || !candidate.url().endsWith(`/api/v1/projects/${project.id}`)) return false
      const body = candidate.request().postDataJSON() as { canvas_data?: Array<{ id?: string; text?: string }> }
      return body.canvas_data?.some(value => value.id === item.id && value.text === updated) === true
    })
    await editor.press('ControlOrMeta+Enter')
    const persisted = await saved
    expect(persisted.ok()).toBeTruthy()
    const current = await persisted.json() as CanvasRecord
    expect(current.canvas_revision).toBeGreaterThan(initial.canvas_revision)
    expect(current.canvas_data).toEqual(expect.arrayContaining([expect.objectContaining({ id: item.id, text: updated })]))
    await page.reload()
    await expect(page.getByTitle(updated, { exact: true })).toBeVisible()

    const stale = await page.request.put(`/api/v1/projects/${project.id}`, {
      headers, data: { canvas_base_revision: initial.canvas_revision, canvas_data: [item] },
    })
    expect(stale.status()).toBe(409)
    await page.reload()
    await expect(page.getByTitle(updated, { exact: true })).toBeVisible()
  })
}
