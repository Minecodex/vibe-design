import { fireEvent, render, screen } from '@testing-library/react'
import type { TFunction } from 'i18next'
import { describe, expect, it, vi } from 'vitest'

import { CanvasWorkspaceMultiSelectToolbar } from './CanvasWorkspaceMultiSelectToolbar'

const testT = ((key: string, fallback?: string) => fallback || key) as unknown as TFunction

describe('CanvasWorkspaceMultiSelectToolbar', () => {
  it('uses internal canvas copy for a multi-selection instead of exporting the selection', () => {
    const handleContextMenuAction = vi.fn()
    const handleBulkExport = vi.fn()

    const { container } = render(
      <CanvasWorkspaceMultiSelectToolbar
        selectedItems={['image-1', 'image-2']}
        canvasItems={[
          { id: 'image-1', type: 'image', x: 10, y: 10, width: 120, height: 90 },
          { id: 'image-2', type: 'image', x: 180, y: 20, width: 140, height: 120 },
        ]}
        getItemDims={(item: any) => ({ width: item.width, height: item.height })}
        canvasRef={{ current: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) } }}
        zoom={100}
        offset={{ x: 0, y: 0 }}
        handleItemMouseDown={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        getCanvasSelectionBorder={() => '1px solid #1677ff'}
        activeTool="select"
        getCanvasSelectionHandleAppearance={() => ({ border: '1px solid #1677ff', backgroundColor: '#fff' })}
        isDark={false}
        handleUngroup={vi.fn()}
        setMultiSelectToolsOpen={vi.fn()}
        multiSelectToolsOpen={null}
        t={testT}
        setGroupBackgroundColor={vi.fn()}
        handleCreateGroup={vi.fn()}
        handleMergeLayers={vi.fn()}
        handleAlign={vi.fn()}
        handleAutoArrange={vi.fn()}
        handleSpacing={vi.fn()}
        handleBulkExport={handleBulkExport}
        handleContextMenuAction={handleContextMenuAction}
      />,
    )

    const toolbarRoot = container.firstElementChild as HTMLDivElement
    expect(toolbarRoot.id).toBe('canvas-screen-preview-selection')
    expect(toolbarRoot.dataset.canvasPreviewScale).toBe('1')

    fireEvent.click(screen.getByLabelText('Copy selection'))

    expect(handleContextMenuAction).toHaveBeenCalledWith('copy')
    expect(handleBulkExport).not.toHaveBeenCalled()
  })

  it('marks a single group toolbar as a screen-space drag preview target', () => {
    const { container } = render(
      <CanvasWorkspaceMultiSelectToolbar
        selectedItems={['group-1']}
        canvasItems={[
          { id: 'group-1', type: 'group', x: 10, y: 10, width: 120, height: 90 },
        ]}
        getItemDims={(item: any) => ({ width: item.width, height: item.height })}
        canvasRef={{ current: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) } }}
        zoom={150}
        offset={{ x: 0, y: 0 }}
        handleItemMouseDown={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        getCanvasSelectionBorder={() => '1px solid #1677ff'}
        activeTool="select"
        getCanvasSelectionHandleAppearance={() => ({ border: '1px solid #1677ff', backgroundColor: '#fff' })}
        isDark={false}
        handleUngroup={vi.fn()}
        setMultiSelectToolsOpen={vi.fn()}
        multiSelectToolsOpen={null}
        t={testT}
        setGroupBackgroundColor={vi.fn()}
        handleCreateGroup={vi.fn()}
        handleMergeLayers={vi.fn()}
        handleAlign={vi.fn()}
        handleAutoArrange={vi.fn()}
        handleSpacing={vi.fn()}
        handleBulkExport={vi.fn()}
        handleContextMenuAction={vi.fn()}
      />,
    )

    const toolbarRoot = container.firstElementChild as HTMLDivElement
    expect(toolbarRoot.id).toBe('canvas-screen-preview-group-1')
    expect(toolbarRoot.dataset.canvasPreviewScale).toBe('1.5')
  })
})
