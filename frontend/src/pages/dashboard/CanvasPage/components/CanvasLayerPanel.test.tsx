import { fireEvent, render, screen } from '@testing-library/react'
import type { TFunction } from 'i18next'
import { describe, expect, it, vi } from 'vitest'

import { CanvasLayerPanel } from './CanvasLayerPanel'

const testT = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction

function renderLayerPanel(itemOverrides: Record<string, any> = {}) {
  const setEditingNameId = vi.fn()

  render(
    <CanvasLayerPanel
      isOpen
      isDark={false}
      t={testT}
      canvasItems={[
        {
          id: 'item-1',
          type: 'image',
          url: 'https://example.com/image.png',
          x: 0,
          y: 0,
          status: 'completed',
          name: 'Sample',
          ...itemOverrides,
        },
      ]}
      selectedItems={[]}
      setSelectedItems={vi.fn()}
      layerDragId={null}
      setLayerDragId={vi.fn()}
      layerDropTarget={null}
      setLayerDropTarget={vi.fn()}
      editingNameId={null}
      setEditingNameId={setEditingNameId}
      updateItem={vi.fn()}
      handleLayerDrop={vi.fn()}
      handleJumpToItem={vi.fn()}
      handleContextMenuAction={vi.fn()}
      setContextMenu={vi.fn()}
      setActiveContextMenuItem={vi.fn()}
      setIsLayerPanelOpen={vi.fn()}
    />,
  )

  return { setEditingNameId }
}

describe('CanvasLayerPanel', () => {
  it('does not allow renaming generating media items from the layer list', () => {
    const { setEditingNameId } = renderLayerPanel({
      type: 'video',
      status: 'generating',
      name: 'Generating video',
    })

    fireEvent.doubleClick(screen.getByText('Generating video'))

    expect(setEditingNameId).not.toHaveBeenCalled()
  })

  it('still allows renaming completed media items from the layer list', () => {
    const { setEditingNameId } = renderLayerPanel()

    fireEvent.doubleClick(screen.getByText('Sample'))

    expect(setEditingNameId).toHaveBeenCalledWith('item-1')
  })
})
