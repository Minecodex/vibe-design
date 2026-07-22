import type React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import type { TFunction } from 'i18next'
import { describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { CanvasContextMenu } from './CanvasContextMenu'

const groupItem: CanvasItem = {
  id: 'group-1',
  type: 'group',
  url: '',
  x: 0,
  y: 0,
  width: 600,
  height: 400,
  name: 'Group 1',
}

const testT = ((_: string, fallback?: string) => fallback || '') as unknown as TFunction

function renderMenu(overrides: Partial<React.ComponentProps<typeof CanvasContextMenu>> = {}) {
  const props: React.ComponentProps<typeof CanvasContextMenu> = {
    contextMenu: { x: 120, y: 80, type: 'item' },
    isDark: false,
    setContextMenu: vi.fn(),
    setActiveContextMenuItem: vi.fn(),
    activeContextMenuItem: 'export',
    selectionContextMenuItems: [{ key: 'export', label: '导出' }],
    firstSelectedItem: groupItem,
    clipboardItems: [],
    canPasteExternalClipboard: false,
    currentSelectionItems: [groupItem],
    selectedItems: ['group-1'],
    handleCreateGroup: vi.fn(),
    handleMergeLayers: vi.fn(),
    handleUngroup: vi.fn(),
    handleBulkExport: vi.fn(),
    handleContextMenuAction: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    resetZoom: vi.fn(),
    handleFitView: vi.fn(),
    t: testT,
    ...overrides,
  }

  render(<CanvasContextMenu {...props} />)
  return props
}

describe('CanvasContextMenu', () => {
  it('shows export format options for a selected group and forwards the chosen image format', () => {
    const props = renderMenu()

    expect(screen.getByText('PNG')).toBeInTheDocument()
    expect(screen.getByText('JPG')).toBeInTheDocument()
    expect(screen.getByText('SVG')).toBeInTheDocument()

    fireEvent.click(screen.getByText('JPG'))

    expect(props.handleBulkExport).toHaveBeenCalledWith(['group-1'], 'JPG')
  })

  it('keeps canvas paste enabled when system clipboard paste is available', () => {
    renderMenu({
      contextMenu: { x: 120, y: 80, type: 'canvas' },
      selectionContextMenuItems: [],
      activeContextMenuItem: null,
      firstSelectedItem: null,
      currentSelectionItems: [],
      selectedItems: [],
      canPasteExternalClipboard: true,
    })

    expect(screen.getByText('Ctrl + V').closest('div')).toHaveStyle({ cursor: 'pointer' })
  })

  it('keeps copy enabled for generator-backed canvas items so image/video generator results can still be duplicated', () => {
    const handleContextMenuAction = vi.fn()

    renderMenu({
      selectionContextMenuItems: [{ key: 'copy', label: '复制', shortcut: 'Ctrl + C' }],
      activeContextMenuItem: null,
      firstSelectedItem: {
        id: 'generator-1',
        type: 'image_generator',
        url: 'https://example.com/result.png',
        x: 0,
        y: 0,
        width: 512,
        height: 512,
        name: 'Generated image',
      },
      currentSelectionItems: [{
        id: 'generator-1',
        type: 'image_generator',
        url: 'https://example.com/result.png',
        x: 0,
        y: 0,
        width: 512,
        height: 512,
        name: 'Generated image',
      }],
      selectedItems: ['generator-1'],
      handleContextMenuAction,
    })

    fireEvent.click(screen.getByText('复制'))

    expect(handleContextMenuAction).toHaveBeenCalledWith('copy')
  })

  it('forwards photoshop edit actions from the selection menu', () => {
    const handleContextMenuAction = vi.fn()

    renderMenu({
      selectionContextMenuItems: [{ key: 'ps_edit', label: 'PS 编辑' }],
      activeContextMenuItem: null,
      firstSelectedItem: {
        id: 'image-1',
        type: 'image',
        url: '/api/v1/uploads/canvas/1/source.svg',
        x: 0,
        y: 0,
        width: 512,
        height: 512,
        name: 'Source image',
      },
      currentSelectionItems: [{
        id: 'image-1',
        type: 'image',
        url: '/api/v1/uploads/canvas/1/source.svg',
        x: 0,
        y: 0,
        width: 512,
        height: 512,
        name: 'Source image',
      }],
      selectedItems: ['image-1'],
      handleContextMenuAction,
    })

    fireEvent.click(screen.getByText('PS 编辑'))

    expect(handleContextMenuAction).toHaveBeenCalledWith('ps_edit')
  })
})
