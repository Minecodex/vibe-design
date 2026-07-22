import { expect, test } from '@playwright/test'

test.describe('canvas performance harness', () => {
  test('keeps 1000 stable images in the WebGL path during wheel zoom', async ({ page }) => {
    await page.addInitScript(() => {
      window.__canvasPerfLongTasks = []
      if ('PerformanceObserver' in window) {
        const observer = new PerformanceObserver((list) => {
          window.__canvasPerfLongTasks.push(
            ...list.getEntries().map((entry) => Math.round(entry.duration)),
          )
        })
        observer.observe({ entryTypes: ['longtask'] })
      }
    })

    await page.goto('/__canvas-perf?count=1000')
    await expect(page.getByTestId('canvas-webgl-stage')).toBeVisible()

    const canvas = page.getByTestId('canvas-perf-harness')
    const box = await canvas.boundingBox()
    expect(box).not.toBeNull()
    await page.mouse.move((box?.x ?? 0) + 500, (box?.y ?? 0) + 360)
    await page.keyboard.down('Control')
    for (let index = 0; index < 24; index += 1) {
      await page.mouse.wheel(0, -120)
    }
    await page.keyboard.up('Control')
    await page.waitForTimeout(350)

    const result = await page.evaluate(() => {
      const snapshots = window.__canvasPerfSnapshots || []
      const latest = snapshots[snapshots.length - 1] || null
      const longTasks = window.__canvasPerfLongTasks || []
      return {
        snapshotCount: snapshots.length,
        latest,
        domImages: document.querySelectorAll('[data-canvas-media-img="true"]').length,
        longTaskCount: longTasks.length,
        maxLongTask: longTasks.length ? Math.max(...longTasks) : 0,
      }
    })

    expect(result.snapshotCount).toBeGreaterThan(0)
    expect(result.latest?.renderer).toBe('webgl')
    expect(result.latest?.webglItems).toBeGreaterThan(0)
    expect(result.latest?.webglItems).toBeLessThan(1000)
    expect(result.domImages).toBeLessThanOrEqual(2)
    expect(result.maxLongTask).toBeLessThan(250)
  })
})

declare global {
  interface Window {
    __canvasPerfLongTasks: number[]
  }
}
