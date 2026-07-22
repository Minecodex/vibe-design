import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const hooksDir = resolve(currentDir, 'hooks')
const controllerPath = resolve(hooksDir, 'useCanvasController.tsx')
const controllerSource = readFileSync(controllerPath, 'utf8')
const controllerLineCount = controllerSource.split(/\r?\n/).length

describe('useCanvasController refactor structure', () => {
  it('keeps the top-level controller focused and under 1000 lines', () => {
    expect(controllerLineCount).toBeLessThan(1000)
  })

  it('delegates major domains to dedicated hook modules', () => {
    expect(controllerSource).toContain("from './useCanvasController.viewport'")
    expect(controllerSource).toContain("from './useCanvasController.media'")
    expect(controllerSource).toContain("from './useCanvasController.generators'")
    expect(controllerSource).toContain("from './useCanvasController.crop'")
    expect(controllerSource).toContain("from './useCanvasController.arrangement'")
    expect(controllerSource).toContain("from './useCanvasController.marks'")
    expect(controllerSource).toContain("from './useCanvasViewportActions'")
  })
})
