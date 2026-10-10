import { describe, expect, it } from 'vitest'

import {
  normalizeWorkspaceAttachmentPath,
  requiresWorkspaceAttachmentFetch,
  resolveAttachmentDisplayUrl,
} from './homeChatAttachmentUrls'

describe('homeChatAttachmentUrls', () => {
  it('treats uploaded input assets as workspace attachments', () => {
    const path = 'references/inputs/upload_001/source.png'

    expect(normalizeWorkspaceAttachmentPath(path)).toBe(path)
    expect(requiresWorkspaceAttachmentFetch(path, 'conv_1')).toBe(true)
    expect(resolveAttachmentDisplayUrl(path, 'conv_1')).toContain(
      '/agent/harness/conversations/conv_1/files/',
    )
  })

  it('normalizes legacy files-prefixed input paths into the canonical reference namespace', () => {
    expect(normalizeWorkspaceAttachmentPath('files/assets/inputs/upload_001/source.png'))
      .toBe('references/inputs/upload_001/source.png')
    expect(normalizeWorkspaceAttachmentPath('files/assets/inputs/../../private.txt')).toBeNull()
  })

  it('treats generated reference assets as workspace attachments', () => {
    const path = 'references/generated/generated_image_001/original.png'

    expect(normalizeWorkspaceAttachmentPath(path)).toBe(path)
  })

  it('rejects removed intermediate asset paths', () => {
    expect(normalizeWorkspaceAttachmentPath('assets/intermediate/run-1/intermediate_001/source.png')).toBeNull()
    expect(normalizeWorkspaceAttachmentPath('files/assets/intermediate/run-1/intermediate_001/source.png')).toBeNull()
  })

  it('does not require protected fetch for direct image URLs', () => {
    expect(requiresWorkspaceAttachmentFetch('https://example.com/image.png', 'conv_1')).toBe(false)
    expect(resolveAttachmentDisplayUrl('https://example.com/image.png', 'conv_1')).toBe(
      'https://example.com/image.png',
    )
  })
})
