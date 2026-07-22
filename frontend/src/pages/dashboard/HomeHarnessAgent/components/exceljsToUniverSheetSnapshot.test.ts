import { describe, expect, it } from 'vitest'
import { Workbook } from 'exceljs'

import { loadExceljsWorkbook, loadExceljsWorkbookFromBase64 } from './exceljsWorkbookLoader'
import { exceljsToUniverSheetSnapshot } from './exceljsToUniverSheetSnapshot'

describe('exceljsToUniverSheetSnapshot', () => {
  it('loads base64 xlsx workbooks and maps workbook metadata into the richer snapshot contract', async () => {
    const workbook = new Workbook()
    workbook.views = [{
      x: 0,
      y: 0,
      width: 16000,
      height: 9000,
      firstSheet: 0,
      activeTab: 1,
      visibility: 'visible',
    }]

    const budgetSheet = workbook.addWorksheet('Budget')
    budgetSheet.getRow(1).height = 24
    budgetSheet.getColumn(1).width = 18
    budgetSheet.getColumn(2).width = 22
    budgetSheet.views = [{ state: 'frozen', xSplit: 1, ySplit: 1 }]
    budgetSheet.mergeCells('A1:B1')

    budgetSheet.getCell('A1').value = 'Budget'
    budgetSheet.getCell('A2').value = 'Tea'
    budgetSheet.getCell('B2').value = 18
    budgetSheet.getCell('B2').numFmt = '$#,##0.00'
    budgetSheet.getCell('B2').font = { bold: true, color: { argb: 'FFFF0000' } }
    budgetSheet.getCell('B2').alignment = { horizontal: 'right' }
    budgetSheet.getCell('B3').value = { formula: 'SUM(B2)', result: 18 }
    budgetSheet.getCell('B3').numFmt = '$#,##0.00'
    budgetSheet.getCell('B3').font = { bold: true, color: { argb: 'FFFF0000' } }
    budgetSheet.getCell('B3').alignment = { horizontal: 'right' }

    const summarySheet = workbook.addWorksheet('Summary')
    summarySheet.getCell('A1').value = 'Total'
    summarySheet.getCell('B1').value = { formula: 'Budget!B3', result: 18 }

    const buffer = await workbook.xlsx.writeBuffer()
    const base64 = Buffer.from(buffer).toString('base64')

    const loadedWorkbook = await loadExceljsWorkbookFromBase64(base64)
    const snapshot = exceljsToUniverSheetSnapshot(loadedWorkbook)
    const budgetSheetId = snapshot.sheetOrder[0]
    const summarySheetId = snapshot.sheetOrder[1]

    expect(snapshot.kind).toBe('sheet')
    expect(snapshot.sheetOrder).toHaveLength(2)
    expect(snapshot.activeSheetId).toBe(summarySheetId)
    expect(snapshot.sheets[budgetSheetId]).toMatchObject({
      id: budgetSheetId,
      name: 'Budget',
      rows: {
        0: { h: 36 },
      },
      cols: {
        0: { w: 131 },
        1: { w: 159 },
      },
      merges: [
        { startRow: 0, startCol: 0, endRow: 0, endCol: 1 },
      ],
      freeze: { rowSplit: 1, colSplit: 1 },
      cells: {
        '0:0': { v: 'Budget', t: 's' },
        '1:0': { v: 'Tea', t: 's' },
        '1:1': expect.objectContaining({ v: 18, t: 'n', numFmt: '$#,##0.00' }),
        '2:1': expect.objectContaining({ v: 18, t: 'n', numFmt: '$#,##0.00' }),
      },
    })
    expect(snapshot.sheets[summarySheetId]).toMatchObject({
      id: summarySheetId,
      name: 'Summary',
      cells: {
        '0:0': { v: 'Total', t: 's' },
        '0:1': { v: 18, t: 'n' },
      },
      rows: {},
      cols: {},
      merges: [],
      freeze: null,
    })
    expect(snapshot.styles).toHaveProperty(snapshot.sheets[budgetSheetId].cells['1:1'].styleId as string)
    expect(snapshot.sheets[budgetSheetId].cells['1:1'].styleId).toBe(snapshot.sheets[budgetSheetId].cells['2:1'].styleId)
  })

  it('converts exceljs point row heights into univer pixel heights with CJK-safe leading', () => {
    const workbook = new Workbook()
    const worksheet = workbook.addWorksheet('Preview')

    worksheet.getRow(1).height = 18
    worksheet.getCell('A1').value = '中国历年出生人口数据'

    const snapshot = exceljsToUniverSheetSnapshot(workbook)
    const sheetId = snapshot.sheetOrder[0]

    expect(snapshot.sheets[sheetId].rows).toEqual({
      0: { h: 28 },
    })
  })

  it('converts exceljs column widths into wider univer pixel widths for preview fidelity', () => {
    const workbook = new Workbook()
    const worksheet = workbook.addWorksheet('Preview')

    worksheet.getColumn(1).width = 18
    worksheet.getColumn(2).width = 22

    const snapshot = exceljsToUniverSheetSnapshot(workbook)
    const sheetId = snapshot.sheetOrder[0]

    expect(snapshot.sheets[sheetId].cols).toEqual({
      0: { w: 131 },
      1: { w: 159 },
    })
  })

  it('pools equivalent styles once and keeps stable style ids across repeated mappings', () => {
    const workbook = new Workbook()
    const worksheet = workbook.addWorksheet('Forecast')

    worksheet.getCell('A1').value = 'Amount'
    worksheet.getCell('B1').value = 12
    worksheet.getCell('C1').value = 24

    worksheet.getCell('B1').numFmt = '0.00'
    worksheet.getCell('B1').font = { bold: true }
    worksheet.getCell('C1').numFmt = '0.00'
    worksheet.getCell('C1').font = { bold: true }

    const firstSnapshot = exceljsToUniverSheetSnapshot(workbook)
    const secondSnapshot = exceljsToUniverSheetSnapshot(workbook)
    const sheetId = firstSnapshot.sheetOrder[0]
    const firstStyleId = firstSnapshot.sheets[sheetId].cells['0:1'].styleId
    const secondStyleId = secondSnapshot.sheets[sheetId].cells['0:1'].styleId

    expect(firstStyleId).toBeDefined()
    expect(firstStyleId).toBe(firstSnapshot.sheets[sheetId].cells['0:2'].styleId)
    expect(firstStyleId).toBe(secondStyleId)
    expect(Object.keys(firstSnapshot.styles)).toEqual([firstStyleId as string])
    expect(firstSnapshot.styles[firstStyleId as string]).toMatchObject({
      font: { bold: true },
      numFmt: '0.00',
    })
  })

  it('loads csv input through the normalized loader as a one-sheet workbook', async () => {
    const workbook = await loadExceljsWorkbook({
      fileName: 'budget.csv',
      base64: Buffer.from('Item,Amount\nTea,18\n', 'utf8').toString('base64'),
    })

    const snapshot = exceljsToUniverSheetSnapshot(workbook)
    const sheetId = snapshot.sheetOrder[0]

    expect(snapshot.sheetOrder).toHaveLength(1)
    expect(snapshot.activeSheetId).toBe(sheetId)
    expect(snapshot.sheets[sheetId]).toMatchObject({
      name: 'budget',
      cells: {
        '0:0': { v: 'Item', t: 's' },
        '0:1': { v: 'Amount', t: 's' },
        '1:0': { v: 'Tea', t: 's' },
        '1:1': { v: 18, t: 'n' },
      },
      rows: {},
      cols: {},
      merges: [],
      freeze: null,
    })
    expect(snapshot.styles).toEqual({})
  })
})
