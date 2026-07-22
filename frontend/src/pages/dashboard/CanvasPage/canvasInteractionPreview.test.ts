import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { createCanvasInteractionPreviewController } from './canvasInteractionPreview'

function item(overrides: Partial<CanvasItem>): CanvasItem {
  return {
    id: overrides.id || 'item',
    type: overrides.type || 'image',
    url: overrides.url ?? '/image.png',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 100,
    height: overrides.height ?? 80,
    z_index: overrides.z_index ?? 0,
    ...overrides,
  }
}

describe('CanvasInteractionPreviewController', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('applies DOM transform previews and clears them without committing React state', () => {
    const element = document.createElement('div')
    element.id = 'item-a'
    const child = document.createElement('div')
    child.style.width = '100%'
    child.style.height = '100%'
    element.appendChild(child)
    document.body.appendChild(element)
    const controller = createCanvasInteractionPreviewController()
    const original = item({ id: 'a', x: 10, y: 20, width: 100, height: 80 })

    controller.begin([original])
    controller.apply([item({ id: 'a', x: 30, y: 15, width: 120, height: 90 })])

    expect(element.style.transform).toBe('translate3d(20px, -5px, 0)')
    expect(element.style.width).toBe('120px')
    expect(element.style.height).toBe('90px')
    expect(child.style.width).toBe('120px')
    expect(child.style.height).toBe('90px')
    expect(controller.getLatestItems()?.[0]).toMatchObject({ id: 'a', x: 30, y: 15 })

    controller.clear()

    expect(element.style.transform).toBe('')
    expect(element.style.width).toBe('')
    expect(element.style.height).toBe('')
    expect(child.style.width).toBe('100%')
    expect(child.style.height).toBe('100%')
    expect(controller.getLatestItems()).toBeNull()
  })

  it('mirrors group previews to the fill, handle, label, and screen toolbar elements', () => {
    const itemElement = document.createElement('div')
    itemElement.id = 'item-group'
    const fillElement = document.createElement('div')
    fillElement.id = 'group-fill-group'
    const handlesElement = document.createElement('div')
    handlesElement.id = 'group-handles-group'
    handlesElement.dataset.canvasPreviewResizeChild = 'false'
    const labelElement = document.createElement('div')
    labelElement.id = 'group-label-group'
    labelElement.dataset.canvasPreviewResizeChild = 'false'
    const toolbarElement = document.createElement('div')
    toolbarElement.id = 'canvas-screen-preview-group'
    toolbarElement.dataset.canvasPreviewScale = '2'
    toolbarElement.style.transform = 'translate(-50%, -100%)'
    document.body.append(itemElement, fillElement, handlesElement, labelElement, toolbarElement)
    const controller = createCanvasInteractionPreviewController()
    const original = item({ id: 'group', type: 'group', x: 0, y: 0, width: 200, height: 120 })

    controller.begin([original])
    controller.apply([item({ id: 'group', type: 'group', x: 10, y: 12, width: 240, height: 160 })])

    expect(itemElement.style.transform).toBe('translate3d(10px, 12px, 0)')
    expect(fillElement.style.transform).toBe('translate3d(10px, 12px, 0)')
    expect(handlesElement.style.transform).toBe('translate3d(10px, 12px, 0)')
    expect(labelElement.style.transform).toBe('translate3d(10px, 12px, 0)')
    expect(toolbarElement.style.transform).toBe('translate(-50%, -100%) translate3d(20px, 24px, 0)')
    expect(fillElement.style.width).toBe('240px')
    expect(fillElement.style.height).toBe('160px')

    controller.clear()

    expect(toolbarElement.style.transform).toBe('translate(-50%, -100%)')
    expect(handlesElement.style.transform).toBe('')
  })

  it('mirrors multi-selection previews to the selection overlay', () => {
    const firstElement = document.createElement('div')
    firstElement.id = 'item-a'
    const secondElement = document.createElement('div')
    secondElement.id = 'item-b'
    const selectionElement = document.createElement('div')
    selectionElement.id = 'canvas-screen-preview-selection'
    selectionElement.dataset.canvasPreviewScale = '1.5'
    selectionElement.style.transform = 'translateZ(0)'
    document.body.append(firstElement, secondElement, selectionElement)
    const controller = createCanvasInteractionPreviewController()
    const originalA = item({ id: 'a', x: 10, y: 20, width: 100, height: 80 })
    const originalB = item({ id: 'b', x: 160, y: 40, width: 120, height: 90 })

    controller.begin([originalA, originalB])
    controller.apply([
      item({ id: 'a', x: 30, y: 35, width: 100, height: 80 }),
      item({ id: 'b', x: 180, y: 55, width: 120, height: 90 }),
    ])

    expect(firstElement.style.transform).toBe('translate3d(20px, 15px, 0)')
    expect(secondElement.style.transform).toBe('translate3d(20px, 15px, 0)')
    expect(selectionElement.style.transform).toBe('translateZ(0) translate3d(30px, 22.5px, 0)')

    controller.clear()

    expect(selectionElement.style.transform).toBe('translateZ(0)')
  })

  it('notifies subscribers about transient preview updates and restore policy', () => {
    const controller = createCanvasInteractionPreviewController()
    const listener = vi.fn()
    const unsubscribe = controller.subscribe(listener)
    const original = item({ id: 'a', x: 0, y: 0 })
    const preview = item({ id: 'a', x: 12, y: 16 })

    controller.begin([original])
    controller.apply([preview])
    controller.clear({ restore: false })

    expect(listener).toHaveBeenNthCalledWith(1, [preview], undefined)
    expect(listener).toHaveBeenNthCalledWith(2, null, { restore: false })

    unsubscribe()
    controller.apply([item({ id: 'a', x: 24, y: 32 })])

    expect(listener).toHaveBeenCalledTimes(2)
  })
})
