import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, test } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')

describe('AssetsPage layout', () => {
  test('keeps the asset library inside an internal vertical scroll container', () => {
    expect(source).toContain('data-testid="assets-page-scroll"')
    expect(source).toContain('min-h-0 overflow-y-auto overflow-x-hidden')
  })

  test('refetches the current view from asset preview realtime hints', () => {
    expect(source).toContain("streamRealtimeEvents({ projectId, signal: controller.signal })")
    expect(source).toContain("notification?.name === 'asset.preview.updated'")
    expect(source).toContain("notification.resource?.type === 'asset'")
    expect(source).toContain('window.setTimeout(() => {')
    expect(source).toContain('void reloadCurrentView();')
  })
})
