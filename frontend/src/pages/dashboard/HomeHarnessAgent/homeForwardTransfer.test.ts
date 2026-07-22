import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteHomeForwardTransfer,
  loadHomeForwardTransfer,
  saveHomeForwardTransfer,
  type HomeForwardTransferPayload,
} from './homeForwardTransfer'

function createPayload(overrides: Partial<HomeForwardTransferPayload> = {}): HomeForwardTransferPayload {
  return {
    key: 'home-forward-transfer:test-key',
    createdAt: '2026-04-23T00:00:00.000Z',
    source: 'canvas-agent',
    projectId: 7,
    mode: 'document',
    text: 'Selected assistant reply',
    attachments: [],
    ...overrides,
  }
}

describe('homeForwardTransfer', () => {
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('saves and loads a transfer payload by storage key', () => {
    const payload = createPayload()

    const storageKey = saveHomeForwardTransfer(payload)

    expect(storageKey).toBe(payload.key)
    expect(loadHomeForwardTransfer(storageKey)).toEqual(payload)
  })

  it('preserves structured media references on transferred attachments', () => {
    const payload = createPayload({
      attachments: [
        {
          id: 12,
          url: '/api/v1/uploads/canvas/7/source.png',
          type: 'image',
          origin_kind: 'local_upload',
          source_asset_id: null,
          reference: {
            id: 'home-asset:/api/v1/uploads/canvas/7/source.png',
            kind: 'home_asset',
            media_type: 'image',
            display_name: 'source.png',
            source: {
              type: 'home_asset',
              url: '/api/v1/uploads/canvas/7/source.png',
            },
          },
        },
      ],
    })

    const storageKey = saveHomeForwardTransfer(payload)

    expect(loadHomeForwardTransfer(storageKey)).toEqual(payload)
  })

  it('deletes a transfer payload after it is consumed', () => {
    const payload = createPayload()
    const storageKey = saveHomeForwardTransfer(payload)

    deleteHomeForwardTransfer(storageKey)

    expect(loadHomeForwardTransfer(storageKey)).toBeNull()
  })

  it('returns null for malformed stored data', () => {
    localStorage.setItem('home-forward-transfer:bad', '{"nope":true}')

    expect(loadHomeForwardTransfer('home-forward-transfer:bad')).toBeNull()
  })

  it('returns null when stored json cannot be parsed', () => {
    localStorage.setItem('home-forward-transfer:bad-json', '{bad json')

    expect(loadHomeForwardTransfer('home-forward-transfer:bad-json')).toBeNull()
  })
})
