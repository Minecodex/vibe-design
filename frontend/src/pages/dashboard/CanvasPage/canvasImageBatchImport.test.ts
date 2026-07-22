import { describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { planUploadedCanvasImages, uploadCanvasImageFiles } from './canvasImageBatchImport'

describe('canvas image batch import', () => {
  it('keeps selection order while limiting concurrent uploads', async () => {
    let activeUploads = 0
    let maxActiveUploads = 0
    const releases: Array<() => void> = []

    class MockImage {
      naturalWidth = 640
      naturalHeight = 480
      onload: null | (() => void) = null
      onerror: null | (() => void) = null

      set src(_value: string) {
        queueMicrotask(() => this.onload?.())
      }
    }

    const restoreImage = globalThis.Image
    vi.stubGlobal('Image', MockImage as unknown as typeof Image)

    const uploadFile = vi.fn(async (file: File) => {
      activeUploads += 1
      maxActiveUploads = Math.max(maxActiveUploads, activeUploads)
      await new Promise<void>((resolve) => releases.push(resolve))
      activeUploads -= 1
      return `/${file.name}`
    })

    try {
      const resultPromise = uploadCanvasImageFiles([
        new File(['a'], 'a.png', { type: 'image/png' }),
        new File(['b'], 'b.png', { type: 'image/png' }),
        new File(['c'], 'c.png', { type: 'image/png' }),
        new File(['d'], 'd.png', { type: 'image/png' }),
      ], uploadFile, 2)

      await vi.waitFor(() => expect(releases).toHaveLength(2))
      releases.splice(0).forEach((release) => release())
      await vi.waitFor(() => expect(releases).toHaveLength(2))
      releases.splice(0).forEach((release) => release())

      const result = await resultPromise
      expect(maxActiveUploads).toBe(2)
      expect(result.failedCount).toBe(0)
      expect(result.successful.map((image) => image.url)).toEqual([
        '/a.png',
        '/b.png',
        '/c.png',
        '/d.png',
      ])
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })

  it('plans unique, non-overlapping canvas items above the existing stack', () => {
    const existingItems: CanvasItem[] = [{
      id: 'existing',
      type: 'image',
      url: '/existing.png',
      x: -50,
      y: -50,
      width: 100,
      height: 100,
      z_index: 4,
    }]
    const ids = ['upload-a', 'upload-b']

    const items = planUploadedCanvasImages([
      { url: '/a.png', width: 100, height: 100 },
      { url: '/b.png', width: 100, height: 100 },
    ], existingItems, { x: 0, y: 0 }, () => ids.shift() || 'unexpected')

    expect(items.map((item) => item.id)).toEqual(['upload-a', 'upload-b'])
    expect(items.map((item) => item.z_index)).toEqual([5, 6])
    expect(items[0].x === items[1].x && items[0].y === items[1].y).toBe(false)
    expect(items.every((item) => item.asset_origin === 'local_upload')).toBe(true)
  })

  it('keeps successful images when another upload fails', async () => {
    class MockImage {
      naturalWidth = 320
      naturalHeight = 240
      onload: null | (() => void) = null
      onerror: null | (() => void) = null

      set src(_value: string) {
        queueMicrotask(() => this.onload?.())
      }
    }

    const restoreImage = globalThis.Image
    vi.stubGlobal('Image', MockImage as unknown as typeof Image)

    try {
      const result = await uploadCanvasImageFiles([
        new File(['ok'], 'ok.png', { type: 'image/png' }),
        new File(['bad'], 'bad.png', { type: 'image/png' }),
      ], async (file) => {
        if (file.name === 'bad.png') throw new Error('upload failed')
        return '/ok.png'
      })

      expect(result.successful).toEqual([{ url: '/ok.png', width: 320, height: 240 }])
      expect(result.failedCount).toBe(1)
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })
})
