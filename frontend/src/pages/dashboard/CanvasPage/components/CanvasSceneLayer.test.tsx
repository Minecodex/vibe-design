import { installCanvas2dContextFixture } from '@/store/testing/canvas2dContextFixture'
import { render, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { CanvasSceneLayer } from './CanvasSceneLayer'

function createItem(overrides: Partial<CanvasItem> = {}): CanvasItem {
  return {
    id: overrides.id || 'item-1',
    type: overrides.type || 'image_generator',
    url: overrides.url || '',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 320,
    height: overrides.height ?? 180,
    z_index: overrides.z_index ?? 0,
    status: overrides.status ?? 'completed',
    ...overrides,
  }
}

describe('CanvasSceneLayer', () => {
  const context = {
    clearRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    roundRect: vi.fn(),
    drawImage: vi.fn(),
    fillText: vi.fn(),
    arc: vi.fn(),
    scale: vi.fn(),
  } as unknown as CanvasRenderingContext2D

  let contextFixture: ReturnType<typeof installCanvas2dContextFixture>
  afterEach(() => contextFixture?.mockRestore())
  beforeEach(() => {
    vi.clearAllMocks()
    contextFixture = installCanvas2dContextFixture(context)
  })

  it('draws accelerated low-zoom items into the scene canvas', async () => {
    const onReadyChange = vi.fn()
    const canvasRef = {
      current: {
        clientWidth: 1200,
        clientHeight: 800,
      },
    } as React.MutableRefObject<HTMLDivElement | null>

    render(
      <CanvasSceneLayer
        canvasRef={canvasRef}
        canvasItems={Array.from({ length: 14 }, (_, index) =>
          createItem({
            id: `image-${index}`,
            type: 'image',
            url: `/image-${index}.png`,
            x: 10 + index * 30,
            y: 10 + index * 20,
          }),
        )}
        selectedItems={['selected-image']}
        marks={[]}
        cropState={null}
        textRedrawExtractingItemIds={new Set<string>()}
        zoom={40}
        offset={{ x: 0, y: 0 }}
        isDark={false}
        getItemDims={(item: CanvasItem) => ({ width: item.width || 1, height: item.height || 1 })}
        onReadyChange={onReadyChange}
      />,
    )

    await waitFor(() => {
      expect(context.clearRect).toHaveBeenCalled()
      expect(context.fillRect).toHaveBeenCalled()
      expect(onReadyChange).toHaveBeenCalledWith(true)
    })
  })

  it('measures the mounted canvas container and renders on first paint without requiring a click rerender', async () => {
    function Harness() {
      const hostRef = React.useRef<HTMLDivElement | null>(null)

      return (
        <div
          ref={(node) => {
            if (!node) {
              hostRef.current = null
              return
            }
            Object.defineProperty(node, 'clientWidth', {
              configurable: true,
              value: 1200,
            })
            Object.defineProperty(node, 'clientHeight', {
              configurable: true,
              value: 800,
            })
            node.getBoundingClientRect = () => ({
              width: 1200,
              height: 800,
              top: 0,
              left: 0,
              right: 1200,
              bottom: 800,
              x: 0,
              y: 0,
              toJSON: () => ({}),
            })
            hostRef.current = node
          }}
          style={{ width: 1200, height: 800 }}
        >
          <CanvasSceneLayer
            canvasRef={hostRef}
            canvasItems={Array.from({ length: 14 }, (_, index) =>
              createItem({
                id: `first-paint-${index}`,
                type: 'image',
                url: `/first-paint-${index}.png`,
                x: 10 + index * 30,
                y: 10 + index * 20,
              }),
            )}
            selectedItems={[]}
            marks={[]}
            cropState={null}
            textRedrawExtractingItemIds={new Set<string>()}
          zoom={40}
          offset={{ x: 0, y: 0 }}
          isDark={false}
          getItemDims={(item: CanvasItem) => ({ width: item.width || 1, height: item.height || 1 })}
          onReadyChange={() => {}}
        />
      </div>
    )
    }

    render(<Harness />)

    await waitFor(() => {
      expect(context.clearRect).toHaveBeenCalled()
    })
  })

  it('redraws the scene when an image asset finishes loading without needing an external rerender', async () => {
    const drawImage = vi.fn()
    installCanvas2dContextFixture({ ...context, drawImage })

    const originalImage = globalThis.Image
    class MockImage {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      decoding = 'async'

      set src(_value: string) {
        queueMicrotask(() => {
          this.onload?.()
        })
      }
    }

    globalThis.Image = MockImage as unknown as typeof Image

    const canvasRef = {
      current: {
        clientWidth: 1200,
        clientHeight: 800,
      },
    } as React.MutableRefObject<HTMLDivElement | null>

    render(
      <CanvasSceneLayer
        canvasRef={canvasRef}
        canvasItems={[
          createItem({ id: 'loaded-image', type: 'image', url: '/loaded.png', x: 10, y: 10 }),
          ...Array.from({ length: 13 }, (_, index) =>
            createItem({
              id: `image-${index}`,
              type: 'image',
              url: `/image-${index}.png`,
              x: 60 + index * 30,
              y: 20 + index * 10,
            }),
          ),
        ]}
        selectedItems={[]}
        marks={[]}
        cropState={null}
        textRedrawExtractingItemIds={new Set<string>()}
        zoom={40}
        offset={{ x: 0, y: 0 }}
        isDark={false}
        getItemDims={(item: CanvasItem) => ({ width: item.width || 1, height: item.height || 1 })}
        onReadyChange={() => {}}
      />,
    )

    await waitFor(() => {
      expect(drawImage).toHaveBeenCalled()
    })

    globalThis.Image = originalImage
  })
})
