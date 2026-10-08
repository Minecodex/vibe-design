import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { HomeChatOfficeSheetSnapshot } from './homeChatOfficeSnapshots'

const createWorkbookMock = vi.fn()
const addEventMock = vi.fn(() => ({ dispose: vi.fn() }))
const disposeMock = vi.fn()
function createFakeUniverSurface() { return {
  univerAPI: {
    createWorkbook: createWorkbookMock,
    addEvent: addEventMock,
    dispose: disposeMock,
    Event: {
      SheetEditEnded: 'SheetEditEnded',
    },
  },
} }
const createUniverMock = vi.fn<(config: unknown) => ReturnType<typeof createFakeUniverSurface>>(createFakeUniverSurface)
const presetConfigSpy = vi.fn((config: unknown) => config)

vi.mock('@univerjs/presets', () => ({
  createUniver: (config: unknown) => createUniverMock(config),
}))

vi.mock('@univerjs/preset-sheets-core', () => ({
  UniverSheetsCorePreset: (config: unknown) => presetConfigSpy(config),
}))

vi.mock('./homeChatUniverSheetLocale', () => ({
  resolveSheetUniverLocale: () => ({}),
}))

describe('HomeChatUniverSheetEditor', () => {
  beforeEach(() => {
    createWorkbookMock.mockReset()
    addEventMock.mockReset()
    addEventMock.mockReturnValue({ dispose: vi.fn() })
    disposeMock.mockReset()
    createUniverMock.mockClear()
    presetConfigSpy.mockClear()
  })

  it('renders a preview-only univer surface without warning chrome or editing toolbars', async () => {
    const { HomeChatUniverSheetEditor } = await import('./HomeChatUniverSheetEditor')
    const snapshot: HomeChatOfficeSheetSnapshot = {
      kind: 'sheet',
      warning: 'Preview keeps formulas without recalculation.',
      sheetOrder: ['sheet-1'],
      activeSheetId: 'sheet-1',
      styles: {},
      sheets: {
        'sheet-1': {
          id: 'sheet-1',
          name: 'Sheet1',
          rows: {},
          cols: {},
          cells: {
            '0:0': { v: 'Year', t: 's' },
          },
          merges: [],
          freeze: null,
        },
      },
    }

    render(<HomeChatUniverSheetEditor snapshot={snapshot} isDark={false} />)

    expect(await screen.findByTestId('home-chat-univer-sheet-editor')).toBeInTheDocument()
    expect(screen.queryByText('Preview keeps formulas without recalculation.')).not.toBeInTheDocument()
    expect(createUniverMock).toHaveBeenCalledWith(expect.objectContaining({
      darkMode: false,
      presets: [expect.objectContaining({
        header: false,
        toolbar: false,
        formulaBar: false,
        footer: true,
        contextMenu: false,
        sheets: {
          disableEdit: true,
        },
      })],
    }))
  })
})
