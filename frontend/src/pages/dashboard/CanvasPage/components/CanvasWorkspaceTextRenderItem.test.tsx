import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { normalizeTextCanvasItem } from '../textTypography'
import { CanvasWorkspaceTextRenderItem } from './CanvasWorkspaceTextRenderItem'

describe('CanvasWorkspaceTextRenderItem', () => {
  it('matches the image selection border and corner handle styling when selected', () => {
    const item: CanvasItem = {
      id: 'text-1',
      type: 'text',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 120,
      text: 'hello',
      fontFamily: 'Instrument Sans',
      fontVariant: 'Regular',
      fontSize: 32,
      fillColor: '#111111',
      lineHeight: 1.2,
      textAlign: 'left',
      z_index: 5,
    }

    const { container } = render(
      <CanvasWorkspaceTextRenderItem
        item={item}
        canvasItems={[item]}
        normalizedTextItem={normalizeTextCanvasItem(item)}
        isHidden={false}
        isItemSelected
        actualWidth={240}
        actualHeight={120}
        selectedItems={['text-1']}
        clampCanvasStackZIndex={(value = 0) => value}
        activeTool="select"
        textEditingItemId={null}
        handleStartTextEdit={vi.fn()}
        handleCommitTextEdit={vi.fn()}
        handleCancelTextEdit={vi.fn()}
        handleItemMouseDown={vi.fn()}
        setSelectedItems={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
        beginTransaction={vi.fn()}
        setActiveGuides={vi.fn()}
        movingItemIdsRef={{ current: new Set() }}
        setMediaResizeState={vi.fn()}
        resizingHandle={{ current: null }}
        dragItemStart={{ current: null }}
        resizingStart={{ current: null }}
        mediaSelectionMetrics={{ handleSize: 12, handleOffset: 6, borderWidth: 2 }}
        getCanvasSelectionHandleAppearance={({ borderWidth }: { borderWidth: number }) => ({
          border: `${borderWidth}px solid rgb(59, 130, 246)`,
          backgroundColor: '#fff',
        })}
        isDark={false}
      />,
    )

    const selectedFrame = container.querySelector('#item-text-1 > div > div') as HTMLElement
    expect(selectedFrame.style.outline).toBe('2px solid rgb(59, 130, 246)')

    const handles = Array.from(container.querySelectorAll('div')).filter((node) => {
      const element = node as HTMLElement
      return element.style.cursor.includes('resize')
    }) as HTMLElement[]

    expect(handles).toHaveLength(4)
    expect(handles[0].style.width).toBe('12px')
    expect(handles[0].style.height).toBe('12px')
    expect(handles[0].style.border).toBe('2px solid rgb(59, 130, 246)')
  })
})
