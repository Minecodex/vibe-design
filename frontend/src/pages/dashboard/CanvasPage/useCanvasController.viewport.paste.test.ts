import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasController.viewport.tsx'),
  'utf8',
)

describe('useCanvasController viewport paste shortcuts', () => {
  it('does not preempt Ctrl+V in keydown so the native paste event resolves internal vs external', () => {
    // Regression: a sticky clipboardSource='internal' flag must never force an
    // internal paste from the keydown handler, otherwise an external/OS image can
    // never reach the canvas after a previous canvas copy. Paste is resolved by
    // the native `paste` handlers (runNativePasteFromClipboardData) instead, which
    // read the live clipboard.
    expect(source).not.toContain("clipboardSource === 'internal'")
    expect(source).not.toMatch(/event\.key\.toLowerCase\(\) === 'v'[\s\S]{0,240}handleContextMenuAction\('paste'\)/)
  })
})
