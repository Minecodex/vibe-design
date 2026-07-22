import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const controllerSource = readFileSync(resolve(currentDir, 'hooks', 'useCanvasController.tsx'), 'utf8')
const viewportActionsSource = readFileSync(resolve(currentDir, 'hooks', 'useCanvasViewportActions.ts'), 'utf8')
const mediaSource = readFileSync(resolve(currentDir, 'hooks', 'useCanvasController.media.ts'), 'utf8')
const generatorsSource = readFileSync(resolve(currentDir, 'hooks', 'useCanvasController.generators.ts'), 'utf8')
const canvasPageSource = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')

describe('canvas generation focus wiring', () => {
  it('defines a shared select-and-center helper in the viewport actions hook', () => {
    expect(controllerSource).toContain("from './useCanvasViewportActions'")
    expect(viewportActionsSource).toContain('const selectAndCenterCanvasItem = useCallback(')
    expect(viewportActionsSource).toContain('setSelectedItems([item.id])')
    expect(viewportActionsSource).toContain('getCenteredCanvasOffset({')
  })

  it('passes the helper into media and generator controllers', () => {
    expect(controllerSource).toContain('selectAndCenterCanvasItem,')
  })

  it('passes the helper into the chat agent canvas update hook', () => {
    expect(canvasPageSource).toContain('selectAndCenterCanvasItem,')
  })

  it('focuses newly created image action placeholders and cutout results', () => {
    expect(mediaSource).toContain('selectAndCenterCanvasItem(resultItem)')
    expect(mediaSource).toContain('selectAndCenterCanvasItem(placeholder)')
  })

  it('focuses newly created generator items and anchored video tasks', () => {
    expect(generatorsSource).toContain('selectAndCenterCanvasItem(newItem)')
    expect(generatorsSource).toContain('selectAndCenterCanvasItem(taskItem)')
  })
})
