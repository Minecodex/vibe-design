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
const canvasAreaSource = readFileSync(resolve(currentDir, 'components', 'CanvasWorkspaceCanvasArea.tsx'), 'utf8')
const itemLayerPath = resolve(currentDir, 'components', 'CanvasWorkspaceItemLayer.tsx')
const itemLayerSource = existsSync(itemLayerPath)
  ? readFileSync(itemLayerPath, 'utf8')
  : ''
const textRenderItemPath = resolve(currentDir, 'components', 'CanvasWorkspaceTextRenderItem.tsx')
const textRenderItemSource = existsSync(textRenderItemPath)
  ? readFileSync(textRenderItemPath, 'utf8')
  : ''
const toolbarSource = readFileSync(resolve(currentDir, 'components', 'CanvasTextToolbar.tsx'), 'utf8')
const textItemSource = readFileSync(resolve(currentDir, 'components', 'CanvasTextItem.tsx'), 'utf8')
const projectsEndpointSource = readFileSync(resolve(currentDir, '..', '..', '..', 'api', 'endpoints', 'projects.ts'), 'utf8')

describe('canvas text tool wiring', () => {
  it('adds a first-class text item type to the persisted canvas item contract', () => {
    expect(projectsEndpointSource).toContain("'text'")
    expect(projectsEndpointSource).toContain('fontFamily')
    expect(projectsEndpointSource).toContain('fontVariant')
    expect(projectsEndpointSource).toContain('writingMode')
  })

  it('defines a dedicated text tool alongside the existing left toolbar actions', () => {
    expect(toolDefinitionSource).toContain("key: 'text'")
    expect(toolDefinitionSource).toContain("label: t('canvas.tools.text'")
  })

  it('wires text creation and editing state from the controller into the workspace', () => {
    expect(controllerSource).toContain('textEditingItemId')
    expect(controllerSource).toContain('textToolbarState')
    expect(pageSource).toContain('textEditingItemId,')
    expect(pageSource).toContain('textToolbarState,')
    expect(pageSource).toContain('handlePlaceTextAtPoint,')
    expect(pageSource).toContain('updateTextStyle,')
    expect(pageSource).toContain('textEditingItemId={textEditingItemId}')
    expect(pageSource).toContain('textToolbarState={textToolbarState}')
    expect(pageSource).toContain('handlePlaceTextAtPoint={handlePlaceTextAtPoint}')
    expect(pageSource).toContain('updateTextStyle={updateTextStyle}')
  })

  it('teaches viewport keyboard handling about the text placement tool', () => {
    expect(viewportSource).toContain("if (event.key === 't' || event.key === 'T') setActiveTool('text')")
  })

  it('renders text items and a typography toolbar in the workspace', () => {
    expect(workspaceSource).toContain('CanvasTextToolbar')
    expect(itemLayerSource).toContain('CanvasWorkspaceTextRenderItem')
    expect(textRenderItemSource).toContain("item.type !== 'text'")
    expect(workspaceSource).toContain('<CanvasWorkspaceCanvasArea {...props} />')
    expect(canvasAreaSource).toContain('handleMouseDown(event)')
    expect(viewportSource).toContain('handlePlaceTextAtPoint(position)')
    expect(textRenderItemSource).toContain('textEditingItemId')
    expect(workspaceSource).toContain('updateTextStyle')
  })

  it('keeps text editable after selection and exposes descriptive toolbar affordances', () => {
    expect(textRenderItemSource).toContain('handleStartTextEdit(item.id)')
    expect(textItemSource).toContain('title=')
    expect(toolbarSource).toContain('title={label}')
    expect(toolbarSource).toContain('aria-label={label}')
  })

  it('supports the extended size list and per-button popovers shown above the active control', () => {
    expect(toolbarSource).toContain('9999')
    expect(toolbarSource).toContain('const TOOLBAR_SCALE = 0.65')
    expect(toolbarSource).toContain('const POPOVER_SCALE = Number((TOOLBAR_SCALE * 1.3).toFixed(3))')
    expect(toolbarSource).toContain("bottom: 'calc(100% + 12px)'")
    expect(toolbarSource).toContain("left: '50%'")
    expect(toolbarSource).toContain('scale(${POPOVER_SCALE})')
    expect(toolbarSource).toContain("document.addEventListener('pointerdown', handlePointerDown)")
  })

  it('includes explicit none states for more-panel transform and list controls', () => {
    expect(toolbarSource).toContain("{ key: 'none', label: '-', value: textItem.textTransform === 'none' }")
    expect(toolbarSource).toContain("{ key: 'none', label: '-', value: textItem.listStyle === 'none' }")
    expect(toolbarSource).toContain("label=\"水平\"")
  })

  it('renders an expanded color picker panel and keeps the font list compact', () => {
    expect(toolbarSource).toContain("field === 'fillColor' ? labels.fill : labels.stroke")
    expect(toolbarSource).toContain('type="range"')
    expect(toolbarSource).toContain('opacityPercent')
    expect(toolbarSource).toContain('fontSize: 22')
    expect(toolbarSource).toContain('maxHeight: 300')
  })
})
