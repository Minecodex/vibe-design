import type {
  HomeChatOfficeSheetSnapshot,
  HomeChatOfficeWorkbookCellSnapshot,
  HomeChatOfficeWorkbookSheetSnapshot,
} from './homeChatOfficeSnapshots'

const DEFAULT_WORKBOOK_ID = 'workbook-1'
const DEFAULT_WORKBOOK_NAME = 'Workbook'
const DEFAULT_APP_VERSION = '0.21.0'
const DEFAULT_LOCALE = 'enUS'

function mapCellTypeToPayloadType(cellType: unknown): HomeChatOfficeWorkbookCellSnapshot['t'] {
  switch (cellType) {
    case 1:
      return 's'
    case 2:
      return 'n'
    case 3:
      return 'b'
    case 4:
      return 's'
    case 's':
    case 'n':
    case 'b':
    case 'd':
    case 'e':
      return cellType
    default:
      return null
  }
}

function mapPayloadTypeToCellType(cellType: unknown): number | undefined {
  switch (cellType) {
    case 's':
    case 'd':
    case 'e':
      return 1
    case 'n':
      return 2
    case 'b':
      return 3
    default:
      return undefined
  }
}

function isWorkbookSheetSnapshot(snapshot: HomeChatOfficeSheetSnapshot | null | undefined): snapshot is HomeChatOfficeWorkbookSheetSnapshot {
  return Boolean(
    snapshot
    && Array.isArray((snapshot as HomeChatOfficeWorkbookSheetSnapshot).sheetOrder)
    && !Array.isArray((snapshot as HomeChatOfficeWorkbookSheetSnapshot).sheets),
  )
}

export function getLegacyFirstSheet(snapshot: HomeChatOfficeSheetSnapshot | null | undefined) {
  if (!snapshot || !Array.isArray(snapshot.sheets)) {
    return null
  }

  return snapshot.sheets[0] || null
}

export function toUniverWorkbookData(snapshot: HomeChatOfficeSheetSnapshot | null | undefined): Record<string, any> | null {
  if (!isWorkbookSheetSnapshot(snapshot)) {
    return null
  }

  const sheetOrder = snapshot.sheetOrder.length > 0
    ? snapshot.sheetOrder
    : Object.keys(snapshot.sheets)

  return {
    id: DEFAULT_WORKBOOK_ID,
    name: DEFAULT_WORKBOOK_NAME,
    appVersion: DEFAULT_APP_VERSION,
    locale: DEFAULT_LOCALE,
    sheetOrder,
    styles: snapshot.styles,
    sheets: sheetOrder.reduce<Record<string, any>>((accumulator, sheetId) => {
      const sheet = snapshot.sheets[sheetId]
      if (!sheet) {
        return accumulator
      }

      const cellData = Object.entries(sheet.cells || {}).reduce<Record<string, Record<string, any>>>((rows, [cellKey, cell]) => {
        const [rowIndexText, columnIndexText] = cellKey.split(':')
        const rowIndex = Number(rowIndexText)
        const columnIndex = Number(columnIndexText)
        if (Number.isNaN(rowIndex) || Number.isNaN(columnIndex)) {
          return rows
        }

        rows[rowIndex] ||= {}
        rows[rowIndex][columnIndex] = {
          ...(cell.v !== undefined ? { v: cell.v } : {}),
          ...(cell.t ? { t: mapPayloadTypeToCellType(cell.t) } : {}),
          ...(cell.f ? { f: cell.f } : {}),
          ...(cell.styleId ? { s: cell.styleId } : {}),
        }
        return rows
      }, {})

      accumulator[sheetId] = {
        id: sheet.id,
        name: sheet.name,
        tabColor: '',
        hidden: 0,
        rowCount: 1000,
        columnCount: 26,
        zoomRatio: 1,
        scrollTop: 0,
        scrollLeft: 0,
        defaultColumnWidth: 93,
        defaultRowHeight: 27,
        mergeData: (sheet.merges || []).map((merge) => ({
          startRow: merge.startRow,
          startColumn: merge.startCol,
          endRow: merge.endRow,
          endColumn: merge.endCol,
        })),
        freeze: sheet.freeze
          ? {
              xSplit: sheet.freeze.colSplit || 0,
              ySplit: sheet.freeze.rowSplit || 0,
              startRow: sheet.freeze.rowSplit || 0,
              startColumn: sheet.freeze.colSplit || 0,
            }
          : {
              xSplit: 0,
              ySplit: 0,
              startRow: 0,
              startColumn: 0,
            },
        rowData: sheet.rows || {},
        columnData: sheet.cols || {},
        cellData,
        rowHeader: { width: 46 },
        columnHeader: { height: 20 },
        showGridlines: 1,
        rightToLeft: 0,
      }
      return accumulator
    }, {}),
  }
}

export function univerSheetToWorkbookPayload(workbook: {
  getSnapshot?: () => Record<string, any> | null | undefined
  getActiveSheet?: (allowNull?: boolean) => { getSheetId?: () => string } | null | undefined
} | null | undefined): HomeChatOfficeWorkbookSheetSnapshot {
  const snapshot = workbook?.getSnapshot?.() || {}
  const styles = Object.entries(snapshot.styles || {}).reduce<Record<string, Record<string, unknown>>>((accumulator, [styleId, style]) => {
    if (style && typeof style === 'object') {
      accumulator[styleId] = style as Record<string, unknown>
    }
    return accumulator
  }, {})
  const sheetOrder = Array.isArray(snapshot.sheetOrder) ? snapshot.sheetOrder : Object.keys(snapshot.sheets || {})
  const activeSheetId = workbook?.getActiveSheet?.(true)?.getSheetId?.()
    || sheetOrder[0]
    || 'sheet-1'

  return {
    kind: 'sheet',
    sheetOrder,
    activeSheetId,
    styles,
    sheets: sheetOrder.reduce<Record<string, any>>((accumulator, sheetId) => {
      const sheet = snapshot.sheets?.[sheetId]
      if (!sheet) {
        return accumulator
      }

      const cells = Object.entries(sheet.cellData || {}).reduce<Record<string, HomeChatOfficeWorkbookCellSnapshot>>((cellAccumulator, [rowIndexText, row]) => {
        const rowIndex = Number(rowIndexText)
        if (Number.isNaN(rowIndex) || !row || typeof row !== 'object') {
          return cellAccumulator
        }

        Object.entries(row as Record<string, any>).forEach(([columnIndexText, cell]) => {
          const columnIndex = Number(columnIndexText)
          if (Number.isNaN(columnIndex) || !cell || typeof cell !== 'object') {
            return
          }

          const styleId = typeof cell.s === 'string' ? cell.s : null
          const numFmt = styleId && typeof styles[styleId]?.numFmt === 'string'
            ? (styles[styleId].numFmt as string)
            : null

          cellAccumulator[`${rowIndex}:${columnIndex}`] = {
            ...(cell.v !== undefined ? { v: cell.v } : {}),
            ...(cell.f ? { f: cell.f } : {}),
            ...(styleId ? { styleId } : {}),
            ...(numFmt ? { numFmt } : {}),
            t: mapCellTypeToPayloadType(cell.t),
          }
        })

        return cellAccumulator
      }, {})

      accumulator[sheetId] = {
        id: sheet.id || sheetId,
        name: sheet.name || sheetId,
        rows: Object.entries(sheet.rowData || {}).reduce<Record<string, { h: number }>>((rows, [rowIndex, row]) => {
          if (row && typeof row === 'object' && typeof (row as { h?: unknown }).h === 'number') {
            rows[rowIndex] = { h: (row as { h: number }).h }
          }
          return rows
        }, {}),
        cols: Object.entries(sheet.columnData || {}).reduce<Record<string, { w: number }>>((cols, [columnIndex, column]) => {
          if (column && typeof column === 'object' && typeof (column as { w?: unknown }).w === 'number') {
            cols[columnIndex] = { w: (column as { w: number }).w }
          }
          return cols
        }, {}),
        cells,
        merges: Array.isArray(sheet.mergeData)
          ? sheet.mergeData.map((merge: Record<string, any>) => ({
              startRow: Number(merge.startRow) || 0,
              startCol: Number(merge.startColumn) || 0,
              endRow: Number(merge.endRow) || 0,
              endCol: Number(merge.endColumn) || 0,
            }))
          : [],
        freeze: sheet.freeze && ((sheet.freeze.xSplit || 0) > 0 || (sheet.freeze.ySplit || 0) > 0)
          ? {
              rowSplit: sheet.freeze.ySplit || 0,
              colSplit: sheet.freeze.xSplit || 0,
            }
          : null,
      }
      return accumulator
    }, {}),
  }
}
