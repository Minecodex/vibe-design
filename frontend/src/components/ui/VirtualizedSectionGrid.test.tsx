import { createRef } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { VirtualizedSectionGrid } from './VirtualizedSectionGrid'

type Item = { id: number; label: string }

const resizeObserverInstances: Array<{ callback: ResizeObserverCallback }> = []

class MockResizeObserver {
  callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    resizeObserverInstances.push({ callback })
  }

  observe() {}

  disconnect() {}

  unobserve() {}
}

describe('VirtualizedSectionGrid', () => {
  beforeEach(() => {
    resizeObserverInstances.length = 0
    vi.stubGlobal('ResizeObserver', MockResizeObserver as unknown as typeof ResizeObserver)
  })

  test('renders only the visible rows plus overscan and updates on scroll', async () => {
    const scrollContainerRef = createRef<HTMLDivElement>()
    const items = Array.from({ length: 120 }, (_, index) => ({
      id: index + 1,
      label: `asset-${index + 1}`,
    }))

    const { container } = render(
      <div ref={scrollContainerRef} style={{ height: '600px', overflowY: 'auto' }}>
        <VirtualizedSectionGrid
          scrollContainerRef={scrollContainerRef}
          sections={[{ key: 'all', items }]}
          minColumnWidth={250}
          gap={8}
          overscanRows={1}
          renderItem={(item: Item) => <div>{item.label}</div>}
        />
      </div>,
    )

    const scrollContainer = scrollContainerRef.current
    expect(scrollContainer).not.toBeNull()

    const host = container.querySelector('[data-testid="virtualized-section-grid"]') as HTMLDivElement
    expect(host).not.toBeNull()

    Object.defineProperty(scrollContainer!, 'clientHeight', { configurable: true, value: 600 })
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 1040 })
    Object.defineProperty(host, 'offsetTop', { configurable: true, value: 0 })

    act(() => {
      resizeObserverInstances.forEach(({ callback }) => {
        callback(
          [
            {
              target: host,
              contentRect: { width: 1040, height: 0 } as DOMRectReadOnly,
            } as unknown as ResizeObserverEntry,
          ],
          {} as ResizeObserver,
        )
      })
    })

    await waitFor(() => {
      expect(screen.getByText('asset-1')).toBeInTheDocument()
    })

    expect(screen.queryByText('asset-120')).not.toBeInTheDocument()
    expect(container.textContent?.match(/asset-/g)?.length ?? 0).toBeLessThan(40)

    Object.defineProperty(scrollContainer!, 'scrollTop', { configurable: true, value: 2200 })
    act(() => {
      fireEvent.scroll(scrollContainer!)
    })

    await waitFor(() => {
      expect(screen.getByText('asset-45')).toBeInTheDocument()
    })

    expect(screen.queryByText('asset-1')).not.toBeInTheDocument()
  })

  test('keeps a larger default overscan window to reduce scroll-back remount churn', async () => {
    const scrollContainerRef = createRef<HTMLDivElement>()
    const items = Array.from({ length: 120 }, (_, index) => ({
      id: index + 1,
      label: `asset-${index + 1}`,
    }))

    const { container } = render(
      <div ref={scrollContainerRef} style={{ height: '600px', overflowY: 'auto' }}>
        <VirtualizedSectionGrid
          scrollContainerRef={scrollContainerRef}
          sections={[{ key: 'all', items }]}
          minColumnWidth={250}
          gap={8}
          renderItem={(item: Item) => <div>{item.label}</div>}
        />
      </div>,
    )

    const scrollContainer = scrollContainerRef.current
    expect(scrollContainer).not.toBeNull()

    const host = container.querySelector('[data-testid="virtualized-section-grid"]') as HTMLDivElement
    expect(host).not.toBeNull()

    Object.defineProperty(scrollContainer!, 'clientHeight', { configurable: true, value: 600 })
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 1040 })
    Object.defineProperty(host, 'offsetTop', { configurable: true, value: 0 })

    act(() => {
      resizeObserverInstances.forEach(({ callback }) => {
        callback(
          [
            {
              target: host,
              contentRect: { width: 1040, height: 0 } as DOMRectReadOnly,
            } as unknown as ResizeObserverEntry,
          ],
          {} as ResizeObserver,
        )
      })
    })

    await waitFor(() => {
      expect(screen.getByText('asset-1')).toBeInTheDocument()
    })

    expect(container.textContent?.match(/asset-/g)?.length ?? 0).toBeGreaterThan(28)
  })

  test('keeps item wrappers aligned with fractional grid cell sizes', async () => {
    const scrollContainerRef = createRef<HTMLDivElement>()
    const items = Array.from({ length: 6 }, (_, index) => ({
      id: index + 1,
      label: `asset-${index + 1}`,
    }))

    const { container } = render(
      <div ref={scrollContainerRef} style={{ height: '600px', overflowY: 'auto' }}>
        <VirtualizedSectionGrid
          scrollContainerRef={scrollContainerRef}
          sections={[{ key: 'all', items }]}
          minColumnWidth={250}
          gap={16}
          renderItem={(item: Item) => <div data-testid={`item-${item.id}`}>{item.label}</div>}
        />
      </div>,
    )

    const scrollContainer = scrollContainerRef.current
    expect(scrollContainer).not.toBeNull()

    const host = container.querySelector('[data-testid="virtualized-section-grid"]') as HTMLDivElement
    expect(host).not.toBeNull()

    Object.defineProperty(scrollContainer!, 'clientHeight', { configurable: true, value: 600 })
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 1000 })

    act(() => {
      resizeObserverInstances.forEach(({ callback }) => {
        callback(
          [
            {
              target: host,
              contentRect: { width: 1000, height: 0 } as DOMRectReadOnly,
            } as unknown as ResizeObserverEntry,
          ],
          {} as ResizeObserver,
        )
      })
    })

    await waitFor(() => {
      expect(screen.getByTestId('item-1')).toBeInTheDocument()
    })

    const itemHost = screen.getByTestId('item-1').parentElement as HTMLDivElement
    expect(Number.parseFloat(itemHost.style.height)).toBeCloseTo(322.67, 2)
    expect(Number.parseFloat(itemHost.parentElement?.style.height || '')).toBeCloseTo(322.67, 2)
    expect(Number.parseFloat(itemHost.parentElement?.parentElement?.style.height || '')).toBeCloseTo(338.67, 2)
  })
})
