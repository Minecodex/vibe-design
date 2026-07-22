import { describe, expect, it } from 'vitest'

import { univerSheetToWorkbookPayload } from './univerSheetToWorkbookPayload'

describe('univerSheetToWorkbookPayload', () => {
  it('exports a Univer workbook snapshot into the richer home-chat sheet payload', () => {
    const workbook = {
      getSnapshot: () => ({
        sheetOrder: ['sheet-1', 'sheet-2'],
        styles: {
          'style-1': {
            font: { bold: true },
            numFmt: '$#,##0.00',
          },
        },
        sheets: {
          'sheet-1': {
            id: 'sheet-1',
            name: 'Budget',
            rowData: {
              0: { h: 24 },
            },
            columnData: {
              0: { w: 18 },
              1: { w: 22 },
            },
            cellData: {
              0: {
                0: { v: 'Budget', t: 1 },
                1: { v: 18, t: 2, s: 'style-1' },
              },
              1: {
                0: { v: 'Tea', t: 1 },
                1: { v: 18, t: 2, f: '=SUM(B1)', s: 'style-1' },
              },
            },
            mergeData: [
              { startRow: 0, startColumn: 0, endRow: 0, endColumn: 1 },
            ],
            freeze: { xSplit: 1, ySplit: 1, startRow: 1, startColumn: 1 },
          },
          'sheet-2': {
            id: 'sheet-2',
            name: 'Summary',
            rowData: {},
            columnData: {},
            cellData: {
              0: {
                0: { v: 'Done', t: 1 },
                1: { v: true, t: 3 },
              },
            },
            mergeData: [],
            freeze: { xSplit: 0, ySplit: 0, startRow: 0, startColumn: 0 },
          },
        },
      }),
      getActiveSheet: () => ({
        getSheetId: () => 'sheet-2',
      }),
    }

    expect(univerSheetToWorkbookPayload(workbook as any)).toEqual({
      kind: 'sheet',
      sheetOrder: ['sheet-1', 'sheet-2'],
      activeSheetId: 'sheet-2',
      styles: {
        'style-1': {
          font: { bold: true },
          numFmt: '$#,##0.00',
        },
      },
      sheets: {
        'sheet-1': {
          id: 'sheet-1',
          name: 'Budget',
          rows: {
            0: { h: 24 },
          },
          cols: {
            0: { w: 18 },
            1: { w: 22 },
          },
          cells: {
            '0:0': { v: 'Budget', t: 's' },
            '0:1': { v: 18, t: 'n', styleId: 'style-1', numFmt: '$#,##0.00' },
            '1:0': { v: 'Tea', t: 's' },
            '1:1': { v: 18, t: 'n', f: '=SUM(B1)', styleId: 'style-1', numFmt: '$#,##0.00' },
          },
          merges: [
            { startRow: 0, startCol: 0, endRow: 0, endCol: 1 },
          ],
          freeze: { rowSplit: 1, colSplit: 1 },
        },
        'sheet-2': {
          id: 'sheet-2',
          name: 'Summary',
          rows: {},
          cols: {},
          cells: {
            '0:0': { v: 'Done', t: 's' },
            '0:1': { v: true, t: 'b' },
          },
          merges: [],
          freeze: null,
        },
      },
    })
  })
})
