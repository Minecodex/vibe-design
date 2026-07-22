import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CanvasWorkspaceGroupLayer } from './CanvasWorkspaceGroupLayer'

describe('CanvasWorkspaceGroupLayer', () => {
  it('keeps groups visually behind their contents and matches media selection border/handle styling when selected', () => {
    const handleItemMouseDown = vi.fn()
    const beginTransaction = vi.fn()
    const setActiveGuides = vi.fn()
    const setResizingGroupId = vi.fn()
    const movingItemIdsRef = { current: new Set() }
    const resizingHandle = { current: null as string | null }
    const dragItemStart = { current: null as { x: number; y: number } | null }
    const resizingStart = { current: null as any }

    const { container } = render(
      <CanvasWorkspaceGroupLayer
        canvasItems={[
          {
            id: 'group-1',
            type: 'group',
            x: 100,
            y: 80,
            width: 320,
            height: 180,
            z_index: 8,
            background_color: '#cfe3ff',
          },
        ]}
        selectedItems={['group-1']}
        handleItemMouseDown={handleItemMouseDown}
        setSelectedItems={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        isDark={false}
        getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
        activeTool="select"
        zoom={100}
        offset={{ x: 0, y: 0 }}
        canvasRef={{ current: { clientWidth: 1600, clientHeight: 900 } }}
        setEditingNameId={vi.fn()}
        beginTransaction={beginTransaction}
        setActiveGuides={setActiveGuides}
        movingItemIdsRef={movingItemIdsRef}
        setResizingGroupId={setResizingGroupId}
        resizingHandle={resizingHandle}
        dragItemStart={dragItemStart}
        resizingStart={resizingStart}
        getCanvasSelectionHandleAppearance={({ borderWidth }: { borderWidth: number }) => ({
          border: `${borderWidth}px solid rgb(59, 130, 246)`,
          backgroundColor: '#fff',
        })}
      />,
    )

    const groupFill = container.querySelector('#group-fill-group-1') as HTMLElement
    const group = container.querySelector('#item-group-1') as HTMLElement
    const groupLabel = container.querySelector('#group-label-group-1') as HTMLElement
    const groupHandles = container.querySelector('#group-handles-group-1') as HTMLElement
    expect(groupFill).not.toBeNull()
    expect(group).not.toBeNull()
    expect(groupLabel?.dataset.canvasPreviewResizeChild).toBe('false')
    expect(groupHandles?.dataset.canvasPreviewResizeChild).toBe('false')
    expect(groupFill.style.zIndex).toBe('7')
    expect(group.style.zIndex).toBe('2147483639')
    expect(group.style.border).toBe('2px solid rgb(59, 130, 246)')
    expect(group.style.pointerEvents).toBe('none')

    fireEvent.mouseDown(groupFill, { clientX: 180, clientY: 120, button: 0 })
    expect(handleItemMouseDown).toHaveBeenCalledWith(expect.any(Object), 'group-1')

    const handles = Array.from(container.querySelectorAll('div')).filter((node) => {
      const element = node as HTMLElement
      return element.style.cursor.includes('resize')
    }) as HTMLElement[]

    expect(handles).toHaveLength(4)
    expect(handles[0].style.width).toBe('12px')
    expect(handles[0].style.height).toBe('12px')
    expect(handles[0].style.border).toBe('2px solid rgb(59, 130, 246)')

    fireEvent.mouseDown(handles[0], { clientX: 240, clientY: 160 })
    expect(beginTransaction).toHaveBeenCalled()
    expect(setActiveGuides).toHaveBeenCalledWith([])
    expect(setResizingGroupId).toHaveBeenCalledWith('group-1')
    expect(resizingHandle.current).toBe('nw')
    expect(dragItemStart.current).toEqual({ x: 240, y: 160 })
  })

  const renderGroupLayer = (overrides: Record<string, any> = {}) =>
    render(
      <CanvasWorkspaceGroupLayer
        canvasItems={[
          { id: 'group-1', type: 'group', name: 'My Group', x: 100, y: 80, width: 320, height: 180, z_index: 8 },
        ]}
        selectedItems={[]}
        handleItemMouseDown={vi.fn()}
        setSelectedItems={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        isDark={false}
        getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
        activeTool="select"
        zoom={100}
        offset={{ x: 0, y: 0 }}
        canvasRef={{ current: { clientWidth: 1600, clientHeight: 900 } }}
        editingNameId={null}
        setEditingNameId={vi.fn()}
        updateItem={vi.fn()}
        beginTransaction={vi.fn()}
        setActiveGuides={vi.fn()}
        movingItemIdsRef={{ current: new Set() }}
        setResizingGroupId={vi.fn()}
        resizingHandle={{ current: null }}
        dragItemStart={{ current: null }}
        resizingStart={{ current: null }}
        getCanvasSelectionHandleAppearance={() => ({})}
        {...overrides}
      />,
    )

  it('renders the group name whether the group is selected or not', () => {
    const unselected = renderGroupLayer({ selectedItems: [] })
    expect(within(unselected.container).getByText('My Group')).toBeInTheDocument()
    unselected.unmount()

    const selected = renderGroupLayer({ selectedItems: ['group-1'] })
    expect(within(selected.container).getByText('My Group')).toBeInTheDocument()
  })

  it('enters edit mode on name click and renames the group when not selected', () => {
    const setEditingNameId = vi.fn()
    const { getByText } = renderGroupLayer({ selectedItems: [], setEditingNameId })

    fireEvent.click(getByText('My Group'))
    expect(setEditingNameId).toHaveBeenCalledWith('group-1')
  })

  it('renders an editable input bound to updateItem while editing the name', () => {
    const updateItem = vi.fn()
    const { container } = renderGroupLayer({ selectedItems: [], editingNameId: 'group-1', updateItem })

    const input = container.querySelector('input') as HTMLInputElement
    expect(input).not.toBeNull()
    expect(input.value).toBe('My Group')

    fireEvent.change(input, { target: { value: 'Renamed' } })
    expect(updateItem).toHaveBeenCalledWith('group-1', { name: 'Renamed' })
  })
})
