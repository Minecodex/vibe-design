import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const viewportSource = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasController.viewport.tsx'),
  'utf8',
)
const messageListSource = readFileSync(
  resolve(currentDir, 'MessageList.tsx'),
  'utf8',
)

describe('useCanvasController viewport text selection shortcuts', () => {
  it('marks the agent message list as a protected native text selection region', () => {
    expect(messageListSource).toContain('data-canvas-text-selectable="true"')
  })

  it('only skips canvas modifier shortcuts when the key event still belongs to the protected text-selection region', () => {
    expect(viewportSource).toContain('protectedSelectionOwner')
    expect(viewportSource).not.toContain("(document.activeElement as HTMLElement | null)?.closest?.('[data-canvas-text-selectable=\"true\"]')")
    expect(viewportSource).toContain('const isProtectedSelectionShortcutContext = Boolean(')
    expect(viewportSource).toContain('protectedSelectionOwner')
    expect(viewportSource).toContain('isProtectedSelectionShortcutContext')
    expect(viewportSource).toContain("event.key === 'Control'")
    expect(viewportSource).toContain("event.key === 'Meta'")
  })
})
