import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it, vi } from 'vitest'

import {
  copySingleCanvasImageToSystemClipboard,
  collectCanvasClipboardItems,
  duplicateCanvasClipboardItems,
  findNonOverlappingGroupPosition,
  shiftCanvasItemsOneLayer,
  writeCanvasClipboardToSystemClipboard,
} from './hooks/useCanvasController.arrangement'
import { CANVAS_CLIPBOARD_MIME } from './canvasClipboard'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasController.arrangement.ts'),
  'utf8',
)

describe('useCanvasController arrangement delete flow', () => {
  it('records deleted chat-generated media keys for context-menu and keyboard deletes', () => {
    expect(source).toContain('recordDeletedAgentMediaKey')
    expect(source).toContain("case 'delete'")
    expect(source).toContain('deletedAgentMediaKeys')
  })
})

describe('shiftCanvasItemsOneLayer', () => {
  it('swaps with the next higher layer instead of creating duplicate z-index values', () => {
    const items = [
      { id: 'image-1', type: 'image', url: '/1.png', x: 0, y: 0, z_index: 1 },
      { id: 'image-2', type: 'image', url: '/2.png', x: 0, y: 0, z_index: 2 },
    ]

    const result = shiftCanvasItemsOneLayer(items, ['image-1'], 'forward')
    const moved = result.find((item) => item.id === 'image-1')
    const displaced = result.find((item) => item.id === 'image-2')

    expect(moved?.z_index).toBe(2)
    expect(displaced?.z_index).toBe(1)
    expect(new Set(result.map((item) => item.z_index)).size).toBe(result.length)
  })

  it('swaps with the next lower layer when sending an item backward', () => {
    const items = [
      { id: 'image-1', type: 'image', url: '/1.png', x: 0, y: 0, z_index: 1 },
      { id: 'image-2', type: 'image', url: '/2.png', x: 0, y: 0, z_index: 2 },
    ]

    const result = shiftCanvasItemsOneLayer(items, ['image-2'], 'backward')
    const moved = result.find((item) => item.id === 'image-2')
    const displaced = result.find((item) => item.id === 'image-1')

    expect(moved?.z_index).toBe(1)
    expect(displaced?.z_index).toBe(2)
    expect(new Set(result.map((item) => item.z_index)).size).toBe(result.length)
  })
})

describe('findNonOverlappingGroupPosition', () => {
  it('avoids overlapping nearby groups when choosing a new group position', () => {
    const result = findNonOverlappingGroupPosition({
      target: { x: 0, y: 0, width: 200, height: 200 },
      obstacles: [
        { x: 0, y: 0, width: 200, height: 200 },
        { x: 260, y: 0, width: 160, height: 160 },
      ],
    })

    expect(result).not.toEqual({ x: 0, y: 0 })
    expect(result.x + 200 <= 0 || result.x >= 200 || result.y + 200 <= 0 || result.y >= 200).toBe(true)
  })
})

describe('useCanvasController arrangement group creation flow', () => {
  it('recenters the viewport on the newly created group after creation', () => {
    expect(source).toContain('selectAndCenterCanvasItem(newGroup)')
  })
})

describe('useCanvasController arrangement grouped copy/paste flow', () => {
  it('does not implicitly add a parent group when copying a grouped child item', () => {
    expect(source).not.toMatch(/if \(item\?\.groupId\) \{\s*includedIds\.add\(item\.groupId\)/)
  })

  it('clears stale group references during paste when the source group was not copied', () => {
    expect(source).toMatch(/if \(item\.groupId\) \{\s*if \(idMap\[item\.groupId\]\) \{\s*return \{ \.\.\.item, groupId: idMap\[item\.groupId\] \}\s*\}\s*return \{ \.\.\.item, groupId: undefined \}/)
  })

  it('copies only the selected grouped child item when the group itself is not selected', () => {
    const items = [
      { id: 'group-1', type: 'group', x: 0, y: 0, width: 400, height: 400 },
      { id: 'image-1', type: 'image', groupId: 'group-1', x: 20, y: 30, width: 100, height: 100 },
    ]

    expect(collectCanvasClipboardItems(items, ['image-1'])).toEqual([
      items[1],
    ])
  })

  it('copies the group and all members when the group itself is selected', () => {
    const items = [
      { id: 'group-1', type: 'group', x: 0, y: 0, width: 400, height: 400 },
      { id: 'image-1', type: 'image', groupId: 'group-1', x: 20, y: 30, width: 100, height: 100 },
      { id: 'text-1', type: 'text', groupId: 'group-1', x: 40, y: 60, width: 120, height: 40 },
    ]

    expect(collectCanvasClipboardItems(items, ['group-1'])).toEqual(items)
  })

  it('drops stale group ids during paste when the clipboard payload does not include the parent group', () => {
    const { pastedItems } = duplicateCanvasClipboardItems({
      canvasItems: [],
      clipboardItems: [
        { id: 'image-1', type: 'image', groupId: 'group-legacy', x: 20, y: 30, width: 100, height: 100 },
      ],
      pastePoint: null,
    })

    expect(pastedItems).toHaveLength(1)
    expect(pastedItems[0].groupId).toBeUndefined()
  })

  it('resolves paste from the live system clipboard rather than a sticky internal flag', () => {
    // Regression: paste must not be gated by an in-memory clipboardSource flag.
    // It inspects the real system clipboard so an external/OS image stays
    // pasteable even after the user has copied something inside the canvas.
    expect(source).toContain('inspectSystemClipboardPasteKind()')
    expect(source).toContain('kind?.hasCanvasClipboardMarker')
    expect(source).toContain('kind?.hasImage')
  })
})

describe('copySingleCanvasImageToSystemClipboard', () => {
  it('writes a real image payload to the system clipboard for a single selected canvas image', async () => {
    const blob = new Blob(['fake-image'], { type: 'image/png' })
    const write = vi.fn().mockResolvedValue(undefined)
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => blob,
    })

    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('ClipboardItem', class ClipboardItem {
      items: Record<string, Blob>

      constructor(items: Record<string, Blob>) {
        this.items = items
      }
    })
    vi.stubGlobal('navigator', {
      clipboard: {
        write,
      },
    })

    await copySingleCanvasImageToSystemClipboard({
      id: 'img-1',
      type: 'image',
      url: 'https://example.com/image.png',
    })

    expect(fetchMock).toHaveBeenCalledWith('https://example.com/image.png')
    expect(write).toHaveBeenCalledTimes(1)
    const [clipboardItems] = write.mock.calls[0]
    expect(Array.isArray(clipboardItems)).toBe(true)
    expect(clipboardItems).toHaveLength(1)
    expect(Object.keys((clipboardItems[0]).items)).toContain(CANVAS_CLIPBOARD_MIME)
    expect(Object.keys((clipboardItems[0]).items)).toContain('text/plain')
    expect(Object.keys((clipboardItems[0]).items)).toContain('image/png')
  })

  it('calls clipboard.write before the image fetch resolves so the browser keeps the user gesture', async () => {
    const blob = new Blob(['fake-image'], { type: 'image/png' })
    type FetchResponseShape = { ok: boolean; blob: () => Promise<Blob> }
    let resolveFetch: ((value: FetchResponseShape) => void) | undefined
    const fetchMock = vi.fn().mockImplementation(() => new Promise((resolve) => {
      resolveFetch = resolve
    }))
    const write = vi.fn().mockResolvedValue(undefined)

    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('ClipboardItem', class ClipboardItem {
      items: Record<string, Promise<Blob> | Blob>

      constructor(items: Record<string, Promise<Blob> | Blob>) {
        this.items = items
      }
    })
    vi.stubGlobal('navigator', {
      clipboard: {
        write,
      },
    })

    const copyPromise = copySingleCanvasImageToSystemClipboard({
      id: 'img-1',
      type: 'image',
      url: 'https://example.com/image.png',
    })

    expect(write).toHaveBeenCalledTimes(1)

    expect(resolveFetch).toBeTypeOf('function')

    resolveFetch?.({
      ok: true,
      blob: async () => blob,
    })

    await copyPromise
  })
})

describe('writeCanvasClipboardToSystemClipboard', () => {
  it('writes a custom canvas clipboard marker for multi-item copies so later paste can distinguish canvas content', async () => {
    const write = vi.fn().mockResolvedValue(undefined)

    vi.stubGlobal('ClipboardItem', class ClipboardItem {
      items: Record<string, Blob | Promise<Blob>>

      constructor(items: Record<string, Blob | Promise<Blob>>) {
        this.items = items
      }
    })
    vi.stubGlobal('navigator', {
      clipboard: {
        write,
      },
    })

    await writeCanvasClipboardToSystemClipboard([
      { id: 'group-1', type: 'group', x: 0, y: 0, width: 200, height: 200 },
      { id: 'brush-1', type: 'brush_path', x: 20, y: 30, width: 100, height: 100 },
    ])

    expect(write).toHaveBeenCalledTimes(1)
    const [clipboardItems] = write.mock.calls[0]
    expect(Array.isArray(clipboardItems)).toBe(true)
    expect(clipboardItems).toHaveLength(1)
    expect(Object.keys((clipboardItems[0]).items)).toEqual([CANVAS_CLIPBOARD_MIME, 'text/plain'])
  })
})
