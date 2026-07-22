import {
  type ReactNode,
  type RefObject,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

type VirtualizedSection<T> = {
  key: string
  items: T[]
  title?: ReactNode
}

type HeaderRow = {
  key: string
  kind: 'header'
  title?: ReactNode
  height: number
}

type ItemsRow<T> = {
  key: string
  kind: 'items'
  items: T[]
  height: number
  startIndex: number
}

type VirtualizedRow<T> = HeaderRow | ItemsRow<T>

interface VirtualizedSectionGridProps<T> {
  sections: VirtualizedSection<T>[]
  scrollContainerRef: RefObject<HTMLElement>
  renderItem: (item: T, absoluteIndex: number) => ReactNode
  minColumnWidth?: number
  gap?: number
  overscanRows?: number
  headerHeight?: number
  headerClassName?: string
  itemsRowClassName?: string
}

const DEFAULT_MIN_COLUMN_WIDTH = 250
const DEFAULT_GAP = 8
const DEFAULT_OVERSCAN_ROWS = 6
const DEFAULT_HEADER_HEIGHT = 40

export function VirtualizedSectionGrid<T>({
  sections,
  scrollContainerRef,
  renderItem,
  minColumnWidth = DEFAULT_MIN_COLUMN_WIDTH,
  gap = DEFAULT_GAP,
  overscanRows = DEFAULT_OVERSCAN_ROWS,
  headerHeight = DEFAULT_HEADER_HEIGHT,
  headerClassName,
  itemsRowClassName,
}: VirtualizedSectionGridProps<T>) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [gridWidth, setGridWidth] = useState(0)
  const [gridOffsetTop, setGridOffsetTop] = useState(0)

  useEffect(() => {
    const host = hostRef.current
    if (!host) {
      return
    }

    const measure = () => {
      const scrollContainer = scrollContainerRef.current
      if (!scrollContainer) {
        return
      }

      const nextWidth = host.clientWidth || window.innerWidth || minColumnWidth
      const hostRect = host.getBoundingClientRect()
      const scrollRect = scrollContainer.getBoundingClientRect()
      const nextOffsetTop = hostRect.top - scrollRect.top + scrollContainer.scrollTop

      setGridWidth(nextWidth)
      setGridOffsetTop(nextOffsetTop)
    }

    measure()

    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(() => {
          measure()
        })

    resizeObserver?.observe(host)
    const scrollContainer = scrollContainerRef.current
    if (scrollContainer) {
      resizeObserver?.observe(scrollContainer)
    }

    window.addEventListener('resize', measure)

    return () => {
      resizeObserver?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [minColumnWidth, scrollContainerRef])

  const columns = useMemo(() => {
    const width = gridWidth || window.innerWidth || minColumnWidth
    return Math.max(1, Math.floor((width + gap) / (minColumnWidth + gap)))
  }, [gap, gridWidth, minColumnWidth])

  const itemSize = useMemo(() => {
    const width = gridWidth || window.innerWidth || minColumnWidth
    return Math.max(
      minColumnWidth,
      (width - gap * (columns - 1)) / columns,
    )
  }, [columns, gap, gridWidth, minColumnWidth])

  const rows = useMemo(() => {
    const nextRows: VirtualizedRow<T>[] = []
    let absoluteIndex = 0

    sections.forEach(section => {
      if (section.title) {
        nextRows.push({
          key: `${section.key}-header`,
          kind: 'header',
          title: section.title,
          height: headerHeight,
        })
      }

      for (let index = 0; index < section.items.length; index += columns) {
        const rowItems = section.items.slice(index, index + columns)
        nextRows.push({
          key: `${section.key}-row-${index}`,
          kind: 'items',
          items: rowItems,
          height: itemSize,
          startIndex: absoluteIndex,
        })
        absoluteIndex += rowItems.length
      }
    })

    return nextRows
  }, [columns, gap, headerHeight, itemSize, sections])

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollContainerRef.current,
    observeElementRect: (_instance, callback) => {
      const measure = () => {
        callback({
          width: scrollContainerRef.current?.clientWidth || gridWidth || minColumnWidth,
          height: scrollContainerRef.current?.clientHeight || window.innerHeight || 0,
        })
      }

      measure()
      window.addEventListener('resize', measure)

      return () => {
        window.removeEventListener('resize', measure)
      }
    },
    observeElementOffset: (_instance, callback) => {
      const scrollContainer = scrollContainerRef.current
      if (!scrollContainer) {
        callback(0, false)
        return () => {}
      }

      const handleScroll = () => callback(scrollContainer.scrollTop, false)
      handleScroll()
      scrollContainer.addEventListener('scroll', handleScroll, { passive: true })

      return () => {
        scrollContainer.removeEventListener('scroll', handleScroll)
      }
    },
    estimateSize: index => rows[index].height + (index === rows.length - 1 ? 0 : gap),
    overscan: overscanRows,
    scrollMargin: gridOffsetTop,
    initialRect: {
      width: gridWidth || minColumnWidth,
      height: scrollContainerRef.current?.clientHeight || window.innerHeight || 0,
    },
  })

  const virtualRows = rowVirtualizer.getVirtualItems()

  return (
    <div ref={hostRef} data-testid="virtualized-section-grid" className="relative w-full">
      <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
        {virtualRows.map(virtualRow => {
          const row = rows[virtualRow.index]
          if (!row) {
            return null
          }
          const isLastRow = virtualRow.index === rows.length - 1
          const outerHeight = row.height + (isLastRow ? 0 : gap)

          return (
          <div
            key={row.key}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: outerHeight,
              transform: `translateY(${virtualRow.start - gridOffsetTop}px)`,
            }}
          >
            {row.kind === 'header' ? (
              <div className={headerClassName} style={{ height: row.height }}>{row.title}</div>
            ) : (
              <div
                className={itemsRowClassName}
                style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${columns}, minmax(${minColumnWidth}px, 1fr))`,
                  gap: `${gap}px`,
                  height: row.height,
                }}
              >
                {row.items.map((item, index) => (
                  <div key={row.startIndex + index} style={{ minWidth: 0, height: row.height }}>
                    {renderItem(item, row.startIndex + index)}
                  </div>
                ))}
              </div>
            )}
          </div>
          )
        })}
      </div>
    </div>
  )
}
