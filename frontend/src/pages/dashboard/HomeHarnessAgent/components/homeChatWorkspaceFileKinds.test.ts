import { describe, expect, it } from 'vitest'

import {
  isSessionHtmlFile,
  isSessionRailPreviewFile,
  isSessionTextLikeFile,
} from './homeChatWorkspaceFileKinds'

describe('homeChatWorkspaceFileKinds', () => {
  it('treats html_bundle zip outputs as html-previewable files', () => {
    const file = {
      name: 'site.zip',
      path: 'file_versions/f_site/v0001/source.zip',
      type: 'html_bundle',
    }

    expect(isSessionHtmlFile(file)).toBe(true)
    expect(isSessionRailPreviewFile(file)).toBe(true)
  })

  it('treats web_bundle zip artifacts as html-previewable files', () => {
    const file = {
      name: 'index.zip',
      path: 'published/f_site/v0001/source.zip',
      type: 'web',
      artifact_kind: 'web_bundle',
      artifact_metadata: {
        artifact_kind: 'web_bundle',
        bundle_format: 'zip',
        entry: 'index.html',
      },
    }

    expect(isSessionHtmlFile(file)).toBe(true)
    expect(isSessionRailPreviewFile(file)).toBe(true)
  })

  it('treats plain text and code files as rail-previewable text files', () => {
    expect(isSessionTextLikeFile({ name: 'notes.txt', path: 'notes.txt', type: 'text' })).toBe(true)
    expect(isSessionTextLikeFile({ name: 'config.json', path: 'config.json', type: 'text' })).toBe(true)
    expect(isSessionTextLikeFile({ name: 'script.py', path: 'script.py', type: 'code' })).toBe(true)
    expect(isSessionRailPreviewFile({ name: 'notes.txt', path: 'notes.txt', type: 'text' })).toBe(true)
    expect(isSessionRailPreviewFile({ name: 'script.py', path: 'script.py', type: 'code' })).toBe(true)
  })

  it('keeps markdown on the markdown-specific preview path', () => {
    const file = { name: 'README.md', path: 'README.md', type: 'text' }

    expect(isSessionTextLikeFile(file)).toBe(false)
    expect(isSessionRailPreviewFile(file)).toBe(true)
  })
})
