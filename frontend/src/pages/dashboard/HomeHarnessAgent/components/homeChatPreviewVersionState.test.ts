import { describe, expect, it } from 'vitest'

import { findRuntimePreviewFile } from './homeChatPreviewVersionState'

describe('findRuntimePreviewFile', () => {
  it('finds the prepared runtime entry under work', () => {
    const file = findRuntimePreviewFile('html-ppt-prepared/index.html', [
      {
        file_id: 'f1',
        name: 'index.html',
        path: 'project/html-ppt-prepared/index.html',
        type: 'html',
        size: 1,
        created_at: '2026-05-06T00:00:00Z',
      },
    ] as any)

    expect(file?.path).toBe('project/html-ppt-prepared/index.html')
  })
})
