import { describe, expect, it } from 'vitest'

import {
  CANVAS_CHAT_ATTACHMENT_ACCEPT,
  filterSupportedCanvasChatAttachmentFiles,
  inferCanvasChatAttachmentKind,
} from './chatAttachmentKinds'

describe('canvas chat attachment kinds', () => {
  it('accepts the approved canvas chat upload formats', () => {
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('image/*')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('.txt')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('.md')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('.docx')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('.xlsx')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('.csv')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).toContain('.html')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).not.toContain('.ts')
    expect(CANVAS_CHAT_ATTACHMENT_ACCEPT).not.toContain('.json')
  })

  it('keeps only the supported local files for canvas chat', () => {
    const files = [
      new File(['img'], 'moodboard.png', { type: 'image/png' }),
      new File(['copy'], 'brief.txt', { type: 'text/plain' }),
      new File(['sheet'], 'budget.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
      new File(['markup'], 'landing.html', { type: 'text/html' }),
      new File(['code'], 'script.ts', { type: 'text/typescript' }),
      new File(['config'], 'config.json', { type: 'application/json' }),
    ]

    const { supported, unsupported } = filterSupportedCanvasChatAttachmentFiles(files)

    expect(supported.map((file) => file.name)).toEqual([
      'moodboard.png',
      'brief.txt',
      'budget.xlsx',
      'landing.html',
    ])
    expect(unsupported.map((file) => file.name)).toEqual(['script.ts', 'config.json'])
  })

  it('infers visual and document attachment kinds for cards', () => {
    expect(inferCanvasChatAttachmentKind({ name: 'reference.svg', type: 'image/svg+xml' })).toBe('image')
    expect(inferCanvasChatAttachmentKind({ name: 'brief.md', type: 'text/markdown' })).toBe('text')
    expect(inferCanvasChatAttachmentKind({ name: 'notes.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })).toBe('document')
    expect(inferCanvasChatAttachmentKind({ name: 'report.csv', type: 'text/csv' })).toBe('spreadsheet')
    expect(inferCanvasChatAttachmentKind({ name: 'snippet.html', type: 'text/html' })).toBe('html')
    expect(inferCanvasChatAttachmentKind({ name: 'script.ts', type: 'text/typescript' })).toBe('other')
  })
})
