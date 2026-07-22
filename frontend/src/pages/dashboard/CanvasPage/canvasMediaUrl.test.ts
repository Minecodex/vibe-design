import { describe, expect, it, vi } from 'vitest'

vi.mock('@/config/runtimeConfig', () => ({
  getApiBaseUrl: () => 'http://localhost:8000/api/v1',
}))

describe('resolveCanvasAgentMediaUrl', () => {
  it('normalizes backend-origin api urls to path-only refs', async () => {
    const { normalizeCanvasAgentMediaRef } = await import('./canvasMediaUrl')

    expect(normalizeCanvasAgentMediaRef('http://localhost:8000/api/v1/uploads/generated/image.png')).toBe(
      '/api/v1/uploads/generated/image.png',
    )
  })

  it('normalizes harness workspace-relative paths to path-only refs when a conversation id is available', async () => {
    const { normalizeCanvasAgentMediaRef } = await import('./canvasMediaUrl')

    expect(normalizeCanvasAgentMediaRef('references/generated/generated_image_001/original.png', 'conv-1')).toBe(
      '/api/v1/agent/harness/conversations/conv-1/files/references%2Fgenerated%2Fgenerated_image_001%2Foriginal.png',
    )
  })

  it('maps generated relative paths to generated upload URLs', async () => {
    const { resolveCanvasAgentMediaUrl } = await import('./canvasMediaUrl')

    expect(resolveCanvasAgentMediaUrl('generated/web_search_image.jpg')).toBe(
      'http://localhost:8000/api/v1/uploads/generated/web_search_image.jpg',
    )
    expect(resolveCanvasAgentMediaUrl('/generated/web_search_image.jpg')).toBe(
      'http://localhost:8000/api/v1/uploads/generated/web_search_image.jpg',
    )
  })

  it('leaves absolute web urls untouched', async () => {
    const { resolveCanvasAgentMediaUrl } = await import('./canvasMediaUrl')

    expect(resolveCanvasAgentMediaUrl('https://example.com/image.png')).toBe('https://example.com/image.png')
  })

  it('expands api-relative upload URLs to backend origin', async () => {
    const { resolveCanvasAgentMediaUrl } = await import('./canvasMediaUrl')

    expect(resolveCanvasAgentMediaUrl('/api/v1/uploads/generated/image.png')).toBe(
      'http://localhost:8000/api/v1/uploads/generated/image.png',
    )
  })

  it('maps harness workspace-relative paths through the harness file endpoint when a conversation id is available', async () => {
    const { resolveCanvasAgentMediaUrl } = await import('./canvasMediaUrl')

    expect(resolveCanvasAgentMediaUrl('references/generated/generated_image_001/original.png', 'conv-1')).toBe(
      'http://localhost:8000/api/v1/agent/harness/conversations/conv-1/files/references%2Fgenerated%2Fgenerated_image_001%2Foriginal.png',
    )
  })

  it('maps sandbox workspace asset paths through the harness file endpoint when a conversation id is available', async () => {
    const { resolveCanvasAgentMediaUrl } = await import('./canvasMediaUrl')

    expect(resolveCanvasAgentMediaUrl('sandbox:/references/generated/generated_image_001/original.png', 'conv-1')).toBe(
      'http://localhost:8000/api/v1/agent/harness/conversations/conv-1/files/references%2Fgenerated%2Fgenerated_image_001%2Foriginal.png',
    )
  })
})
