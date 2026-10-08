import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasProjectSync.ts'),
  'utf8',
)

describe('useCanvasController loading flow', () => {
  it('restores persisted canvas data when the page opens', () => {
    expect(source).toContain('initializeState(')
    expect(source).toContain('loadPersistedGeneratorMeta(')
    expect(source).toContain('projectsApi.get(Number(id))')
    expect(source).toContain('setCanvasItemsLoaded(true)')
  })

  it('resets in-memory state when the loaded canvas is empty', () => {
    expect(source).toContain('initializeState([], [])')
  })

  it('prevents autosave from running after an initial project load failure', () => {
    expect(source).toContain('const [canvasLoadFailed, setCanvasLoadFailed] = useState(false)')
    expect(source).toContain('if (isGuest || !canvasItemsLoaded || !id || canvasLoadFailed || isCanvasStaleRef.current) return')
    expect(source).toContain('setCanvasLoadFailed(true)')
  })

  it('loads synced project assets so image detail metadata can render creator and update time', () => {
    expect(source).toContain('assetsApi.list(Number(id))')
    expect(source).toContain('setProjectAssets(')
  })

  it('restores deleted chat-generated media keys from persisted canvas meta', () => {
    expect(source).toContain('deletedAgentMediaKeys')
    expect(source).toContain('normalizeDeletedAgentMediaKeys(')
  })
})
