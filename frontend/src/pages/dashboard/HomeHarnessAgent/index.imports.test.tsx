import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.resetModules()
  vi.unmock('./components/HomeChatUniverSheetEditor')
})

describe('ChatHomePage module loading', () => {
  it('does not import the sheet editor module just to load the homepage shell', async () => {
    let sheetEditorImported = false

    vi.doMock('./components/HomeChatUniverSheetEditor', async () => {
      sheetEditorImported = true
      const actual = await vi.importActual<typeof import('./components/HomeChatUniverSheetEditor')>('./components/HomeChatUniverSheetEditor')
      return actual
    })

    await import('./index')

    expect(sheetEditorImported).toBe(false)
  })
})
