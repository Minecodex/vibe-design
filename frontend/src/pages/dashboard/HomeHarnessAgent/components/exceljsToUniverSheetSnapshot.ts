import type {
  Alignment,
  CellFormulaValue,
  CellHyperlinkValue,
  CellRichTextValue,
  CellSharedFormulaValue,
  CellValue,
  Fill,
  Font,
  Borders,
  Workbook,
  Worksheet,
  WorksheetView,
} from 'exceljs'

interface WorkbookCellSnapshot {
  v?: string | number | boolean | null
  t?: string | null
  f?: string | null
  styleId?: string | null
  numFmt?: string | null
}

interface WorkbookMergeSnapshot {
  startRow: number
  startCol: number
  endRow: number
  endCol: number
}

interface WorkbookFreezeSnapshot {
  rowSplit?: number | null
  colSplit?: number | null
}

interface WorkbookSheetSnapshot {
  id: string
  name: string
  rows: Record<string, { h: number }>
  cols: Record<string, { w: number }>
  cells: Record<string, WorkbookCellSnapshot>
  merges: WorkbookMergeSnapshot[]
  freeze: WorkbookFreezeSnapshot | null
}

export interface UniverWorkbookSheetSnapshot {
  kind: 'sheet'
  sheetOrder: string[]
  activeSheetId: string
  sheets: Record<string, WorkbookSheetSnapshot>
  styles: Record<string, Record<string, unknown>>
}

interface StyleDefinition {
  font?: Partial<Font>
  alignment?: Partial<Alignment>
  fill?: Fill
  border?: Partial<Borders>
  numFmt?: string
}

function convertExcelColumnWidthToUniverWidth(width: number): number {
  if (!Number.isFinite(width) || width <= 0) {
    return 93
  }

  // ExcelJS stores column width in "character" units while Univer expects
  // a rendered width closer to pixels. Matching Excel's common approximation
  // keeps preview columns readable instead of collapsing into narrow slivers.
  return Math.max(48, Math.round((width * 7) + 5))
}

function convertExcelRowHeightToUniverHeight(height: number): number {
  if (!Number.isFinite(height) || height <= 0) {
    return 27
  }

  // ExcelJS row heights are stored in points, while Univer expects CSS pixels.
  // Add a small leading buffer so CJK glyphs and descenders are not clipped.
  return Math.max(27, Math.ceil((height * 96) / 72) + 4)
}

function isFormulaValue(value: CellValue): value is CellFormulaValue | CellSharedFormulaValue {
  return Boolean(value && typeof value === 'object' && 'formula' in value)
}

function isRichTextValue(value: CellValue): value is CellRichTextValue {
  return Boolean(value && typeof value === 'object' && 'richText' in value)
}

function isHyperlinkValue(value: CellValue): value is CellHyperlinkValue {
  return Boolean(value && typeof value === 'object' && 'hyperlink' in value)
}

function sortObject(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((entry) => sortObject(entry))
  }

  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((accumulator, key) => {
        const nestedValue = (value as Record<string, unknown>)[key]
        if (nestedValue !== undefined) {
          accumulator[key] = sortObject(nestedValue)
        }
        return accumulator
      }, {})
  }

  return value
}

function normalizeCellContent(value: CellValue): Pick<WorkbookCellSnapshot, 'v' | 't' | 'f'> | null {
  if (value == null) {
    return null
  }

  if (typeof value === 'string') {
    return { v: value, t: 's' }
  }

  if (typeof value === 'number') {
    return { v: value, t: 'n' }
  }

  if (typeof value === 'boolean') {
    return { v: value, t: 'b' }
  }

  if (value instanceof Date) {
    return { v: value.toISOString(), t: 'd' }
  }

  if (typeof value === 'object') {
    if (isFormulaValue(value)) {
      const formulaValue = normalizeCellContent(value.result ?? null)
      return {
        v: formulaValue?.v ?? null,
        t: formulaValue?.t ?? null,
        f: value.formula,
      }
    }

    if (isRichTextValue(value)) {
      return {
        v: value.richText.map((part) => part.text).join(''),
        t: 's',
      }
    }

    if (isHyperlinkValue(value)) {
      return {
        v: value.text || value.hyperlink,
        t: 's',
      }
    }

    if ('text' in value && typeof value.text === 'string') {
      return { v: value.text, t: 's' }
    }

    if ('error' in value && typeof value.error === 'string') {
      return { v: value.error, t: 'e' }
    }
  }

  return {
    v: String(value),
    t: 's',
  }
}

function buildStyleDefinition(cell: ReturnType<Worksheet['getCell']>): StyleDefinition | null {
  const style: StyleDefinition = {}

  if (cell.font) {
    style.font = sortObject(cell.font) as Partial<Font>
  }
  if (cell.alignment) {
    style.alignment = sortObject(cell.alignment) as Partial<Alignment>
  }
  if (cell.fill) {
    style.fill = sortObject(cell.fill) as Fill
  }
  if (cell.border) {
    style.border = sortObject(cell.border) as Partial<Borders>
  }
  if (cell.numFmt) {
    style.numFmt = cell.numFmt
  }

  return Object.keys(style).length > 0 ? style : null
}

function getStyleId(
  styleDefinition: StyleDefinition | null,
  styles: Record<string, Record<string, unknown>>,
  styleIdsByKey: Map<string, string>,
): string | undefined {
  if (!styleDefinition) {
    return undefined
  }

  const styleKey = JSON.stringify(sortObject(styleDefinition))
  const existingStyleId = styleIdsByKey.get(styleKey)
  if (existingStyleId) {
    return existingStyleId
  }

  const styleId = `style-${styleIdsByKey.size + 1}`
  styleIdsByKey.set(styleKey, styleId)
  styles[styleId] = JSON.parse(styleKey) as Record<string, unknown>
  return styleId
}

function parseCellAddress(address: string): { row: number; col: number } {
  const match = /^([A-Z]+)(\d+)$/.exec(address.toUpperCase())
  if (!match) {
    return { row: 0, col: 0 }
  }

  const [, columnLabel, rowLabel] = match
  let columnNumber = 0
  for (const character of columnLabel) {
    columnNumber = (columnNumber * 26) + (character.charCodeAt(0) - 64)
  }

  return {
    row: Number(rowLabel) - 1,
    col: columnNumber - 1,
  }
}

function parseMergeRange(range: string): WorkbookMergeSnapshot {
  const [startAddress, endAddress] = range.split(':')
  const start = parseCellAddress(startAddress)
  const end = parseCellAddress(endAddress || startAddress)

  return {
    startRow: start.row,
    startCol: start.col,
    endRow: end.row,
    endCol: end.col,
  }
}

function getFreezePane(worksheet: Worksheet): WorkbookFreezeSnapshot | null {
  const sheetViews = Array.isArray(worksheet.views) ? worksheet.views : []
  const frozenView = sheetViews.find((view): view is WorksheetView & { state: 'frozen'; xSplit?: number; ySplit?: number } => (
    view.state === 'frozen'
  ))
  if (!frozenView || (!frozenView.xSplit && !frozenView.ySplit)) {
    return null
  }

  return {
    rowSplit: frozenView.ySplit || 0,
    colSplit: frozenView.xSplit || 0,
  }
}

function getSheetId(worksheet: Worksheet): string {
  return `sheet-${worksheet.id}`
}

function mapSheet(
  worksheet: Worksheet,
  styles: Record<string, Record<string, unknown>>,
  styleIdsByKey: Map<string, string>,
): WorkbookSheetSnapshot {
  const rows: Record<string, { h: number }> = {}
  const cols: Record<string, { w: number }> = {}
  const cells: Record<string, WorkbookCellSnapshot> = {}

  worksheet.eachRow({ includeEmpty: false }, (row, rowIndex) => {
    if (typeof row.height === 'number') {
      rows[String(rowIndex - 1)] = { h: convertExcelRowHeightToUniverHeight(row.height) }
    }

    row.eachCell({ includeEmpty: false }, (cell, columnIndex) => {
      const content = normalizeCellContent(cell.value)
      const styleDefinition = buildStyleDefinition(cell)
      const styleId = getStyleId(styleDefinition, styles, styleIdsByKey)
      if (!content && !styleId && !cell.numFmt) {
        return
      }

      cells[`${rowIndex - 1}:${columnIndex - 1}`] = {
        ...(content || {}),
        ...(styleId ? { styleId } : {}),
        ...(cell.numFmt ? { numFmt: cell.numFmt } : {}),
      }
    })
  })

  worksheet.columns.forEach((column, index) => {
    if (typeof column.width === 'number') {
      cols[String(index)] = { w: convertExcelColumnWidthToUniverWidth(column.width) }
    }
  })

  const merges = ((worksheet.model.merges || []) as string[]).map((range) => parseMergeRange(range))

  return {
    id: getSheetId(worksheet),
    name: worksheet.name,
    rows,
    cols,
    cells,
    merges,
    freeze: getFreezePane(worksheet),
  }
}

function resolveActiveSheetId(workbook: Workbook, sheetOrder: string[]): string {
  const activeTab = workbook.views?.[0]?.activeTab
  if (typeof activeTab === 'number' && activeTab >= 0 && activeTab < sheetOrder.length) {
    return sheetOrder[activeTab]
  }
  return sheetOrder[0] || 'sheet-1'
}

export function exceljsToUniverSheetSnapshot(workbook: Workbook): UniverWorkbookSheetSnapshot {
  const styles: Record<string, Record<string, unknown>> = {}
  const styleIdsByKey = new Map<string, string>()
  const sheets = workbook.worksheets.reduce<Record<string, WorkbookSheetSnapshot>>((accumulator, worksheet) => {
    const sheet = mapSheet(worksheet, styles, styleIdsByKey)
    accumulator[sheet.id] = sheet
    return accumulator
  }, {})
  const sheetOrder = workbook.worksheets.map((worksheet) => getSheetId(worksheet))

  return {
    kind: 'sheet',
    sheetOrder,
    activeSheetId: resolveActiveSheetId(workbook, sheetOrder),
    sheets,
    styles,
  }
}
