import { describe, expect, it, vi } from 'vitest'

import {
  CANVAS_CLIPBOARD_TEXT_PREFIX,
  CANVAS_CLIPBOARD_EVENT_MIME,
  CANVAS_CLIPBOARD_MIME,
  clipboardDataHasCanvasClipboardMarker,
  serializeCanvasClipboardPayload,
  writeCanvasClipboardMarkerToClipboardData,
} from './canvasClipboard'

describe('canvasClipboard', () => {
  it('uses the web custom format prefix required by ClipboardItem custom types', () => {
    expect(CANVAS_CLIPBOARD_MIME.startsWith('web ')).toBe(true)
  })

  it('serializes a versioned payload for custom canvas clipboard writes', () => {
    const payload = serializeCanvasClipboardPayload([
      { id: 'item-1', type: 'image', x: 10, y: 20 },
    ])

    expect(JSON.parse(payload)).toEqual({
      version: 1,
      items: [
        { id: 'item-1', type: 'image', x: 10, y: 20 },
      ],
    })
  })

  it('detects the custom canvas clipboard marker from clipboardData types', () => {
    const clipboardData = {
      types: [CANVAS_CLIPBOARD_EVENT_MIME, 'text/plain'],
      getData: (type: string) => (type === 'text/plain' ? `${CANVAS_CLIPBOARD_TEXT_PREFIX}payload` : ''),
    }

    expect(clipboardDataHasCanvasClipboardMarker(clipboardData as unknown as DataTransfer)).toBe(true)
  })

  it('detects the canvas clipboard marker from a text/plain sentinel payload', () => {
    const clipboardData = {
      types: ['text/plain'],
      getData: (type: string) => (type === 'text/plain' ? `${CANVAS_CLIPBOARD_TEXT_PREFIX}payload` : ''),
    }

    expect(clipboardDataHasCanvasClipboardMarker(clipboardData as unknown as DataTransfer)).toBe(true)
  })

  it('writes the canvas clipboard marker into the native copy event clipboardData payload', () => {
    const setData = vi.fn()
    const clipboardData = { setData } as unknown as DataTransfer
    const items = [{ id: 'group-1', type: 'group', x: 0, y: 0 }]

    expect(writeCanvasClipboardMarkerToClipboardData(clipboardData, items)).toBe(true)
    expect(setData).toHaveBeenCalledWith(
      CANVAS_CLIPBOARD_EVENT_MIME,
      serializeCanvasClipboardPayload(items),
    )
    expect(setData).toHaveBeenCalledWith(
      'text/plain',
      expect.stringContaining(CANVAS_CLIPBOARD_TEXT_PREFIX),
    )
  })
})
