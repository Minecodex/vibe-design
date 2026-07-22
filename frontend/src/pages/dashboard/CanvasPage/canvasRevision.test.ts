import { describe, expect, it } from 'vitest'

import { applyAgentPatchCanvasRevisionSync } from './canvasRevision'

describe('canvas agent patch revision sync', () => {
  it('clears a stale flag that was raised for the same agent patch revision', () => {
    const result = applyAgentPatchCanvasRevisionSync({
      currentRevision: 12,
      isStale: true,
      staleRevision: 12,
    }, 12)

    expect(result).toMatchObject({
      currentRevision: 12,
      isStale: false,
      staleRevision: null,
      revisionChanged: false,
      staleCleared: true,
    })
  })

  it('keeps stale when the server has already moved beyond the agent patch revision', () => {
    const result = applyAgentPatchCanvasRevisionSync({
      currentRevision: 14,
      isStale: true,
      staleRevision: 14,
    }, 12)

    expect(result).toMatchObject({
      currentRevision: 14,
      isStale: true,
      staleRevision: 14,
      revisionChanged: false,
      staleCleared: false,
    })
  })

  it('does not clear stale for deleted agent item patch events', () => {
    const result = applyAgentPatchCanvasRevisionSync({
      currentRevision: 12,
      isStale: true,
      staleRevision: 12,
    }, 12, { resolveStale: false })

    expect(result).toMatchObject({
      currentRevision: 12,
      isStale: true,
      staleRevision: 12,
      revisionChanged: false,
      staleCleared: false,
    })
  })
})
