import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const pageSource = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')
const toolDefinitionSource = readFileSync(resolve(currentDir, 'canvasToolDefinitions.tsx'), 'utf8')
const controllerSource = readFileSync(resolve(currentDir, 'hooks', 'useCanvasController.tsx'), 'utf8')
const viewportSource = readFileSync(resolve(currentDir, 'hooks', 'useCanvasController.viewport.tsx'), 'utf8')
const workspaceSource = readFileSync(resolve(currentDir, 'components', 'CanvasWorkspace.tsx'), 'utf8')
const floatingPanelsPath = resolve(currentDir, 'components', 'CanvasWorkspaceFloatingPanels.tsx')
const floatingPanelsSource = existsSync(floatingPanelsPath)
  ? readFileSync(floatingPanelsPath, 'utf8')
  : ''
const canvasAreaPath = resolve(currentDir, 'components', 'CanvasWorkspaceCanvasArea.tsx')
const canvasAreaSource = existsSync(canvasAreaPath)
  ? readFileSync(canvasAreaPath, 'utf8')
  : ''
const itemLayerPath = resolve(currentDir, 'components', 'CanvasWorkspaceItemLayer.tsx')
const itemLayerSource = existsSync(itemLayerPath)
  ? readFileSync(itemLayerPath, 'utf8')
  : ''
const projectsEndpointSource = readFileSync(resolve(currentDir, '..', '..', '..', 'api', 'endpoints', 'projects.ts'), 'utf8')

describe('canvas brush tool wiring', () => {
  it('adds a persisted brush_path type to the canvas item contract', () => {
    expect(projectsEndpointSource).toContain("'brush_path'")
    expect(projectsEndpointSource).toContain('brushColor')
    expect(projectsEndpointSource).toContain('brushSize')
    expect(projectsEndpointSource).toContain('pathBounds')
    expect(projectsEndpointSource).toContain('points')
  })

  it('defines a dedicated brush tool alongside the existing left toolbar actions', () => {
    expect(toolDefinitionSource).toContain("key: 'brush'")
    expect(toolDefinitionSource).toContain("shortcut: 'P'")
  })

  it('wires brush draft state and editing actions from the controller into the workspace', () => {
    expect(controllerSource).toContain('brushDraft')
    expect(controllerSource).toContain('brushToolState')
    expect(controllerSource).toContain('brushToolbarState')
    expect(controllerSource).toContain('updateBrushItem')
    expect(controllerSource).toContain('size: 12')
    expect(pageSource).toContain('brushDraft,')
    expect(pageSource).toContain('brushToolState,')
    expect(pageSource).toContain('brushToolbarState,')
    expect(pageSource).toContain('updateBrushItem,')
    expect(pageSource).toContain('brushDraft={brushDraft}')
    expect(pageSource).toContain('brushToolState={brushToolState}')
    expect(pageSource).toContain('brushToolbarState={brushToolbarState}')
    expect(pageSource).toContain('updateBrushItem={updateBrushItem}')
  })

  it('teaches viewport keyboard handling and pointer flow about the brush tool', () => {
    expect(viewportSource).toContain("if (event.key === 'p' || event.key === 'P') setActiveTool('brush')")
    expect(viewportSource).toContain("activeTool === 'brush'")
    expect(viewportSource).toContain('createBrushPathCanvasItem')
  })

  it('renders brush previews, brush items, and a brush toolbar in the workspace', () => {
    expect(workspaceSource).toContain('CanvasBrushToolPanel')
    expect(workspaceSource).toContain('CanvasBrushToolbar')
    expect(itemLayerSource).toContain('CanvasBrushItem')
    expect(itemLayerSource).toContain("item.type === 'brush_path'")
    expect(canvasAreaSource).toContain('brushDraft?.points?.length')
    expect(canvasAreaSource).toContain('CanvasBrushDraftPreview')
    expect(floatingPanelsSource).not.toContain('CanvasBrushDraftPreview')
    expect(workspaceSource).toContain('state={brushToolbarState}')
    expect(workspaceSource).toContain('setState={setBrushToolbarState}')
  })

  it('sizes the left brush tool panel for 3-digit input values', () => {
    expect(workspaceSource).toContain('brushToolIndex=')
    expect(readFileSync(resolve(currentDir, 'components', 'CanvasBrushToolPanel.tsx'), 'utf8')).toContain('max="999"')
  })

  it('keeps brush color popovers aligned with the text color picker capabilities', () => {
    const brushToolbarSource = readFileSync(resolve(currentDir, 'components', 'CanvasBrushToolbar.tsx'), 'utf8')
    expect(brushToolbarSource).toContain("'transparent'")
    expect(brushToolbarSource).toContain('opacityPercent')
    expect(brushToolbarSource).toContain('type="number"')
    expect(brushToolbarSource).toContain('%')
  })
})
