export interface HomeChatOfficeLegacySheetSnapshot {
  kind: 'sheet'
  sheets: Array<{
    name: string
    cells: unknown[][]
  }>
  warning?: string
}

export interface HomeChatOfficeWorkbookCellSnapshot {
  v?: string | number | boolean | null
  t?: string | null
  f?: string | null
  styleId?: string | null
  numFmt?: string | null
}

export interface HomeChatOfficeWorkbookMergeSnapshot {
  startRow: number
  startCol: number
  endRow: number
  endCol: number
}

export interface HomeChatOfficeWorkbookFreezeSnapshot {
  rowSplit?: number | null
  colSplit?: number | null
}

export interface HomeChatOfficeWorkbookSheetDataSnapshot {
  id: string
  name: string
  rows: Record<string, { h: number }>
  cols: Record<string, { w: number }>
  cells: Record<string, HomeChatOfficeWorkbookCellSnapshot>
  merges: HomeChatOfficeWorkbookMergeSnapshot[]
  freeze: HomeChatOfficeWorkbookFreezeSnapshot | null
}

export interface HomeChatOfficeWorkbookSheetSnapshot {
  kind: 'sheet'
  sheetOrder: string[]
  activeSheetId: string
  sheets: Record<string, HomeChatOfficeWorkbookSheetDataSnapshot>
  styles: Record<string, Record<string, unknown>>
  warning?: string
}

export type HomeChatOfficeSheetSnapshot =
  | HomeChatOfficeLegacySheetSnapshot
  | HomeChatOfficeWorkbookSheetSnapshot

export interface HomeChatOfficePresentationSnapshot {
  kind: 'presentation'
  slides: Array<{
    title?: string
    bullets?: string[]
  }>
  warning?: string
}

export type HomeChatOfficeSnapshot =
  | HomeChatOfficeSheetSnapshot
  | HomeChatOfficePresentationSnapshot
  | Record<string, any>
  | null
  | undefined

export type HomeChatOfficeSavePayload =
  | HomeChatOfficeWorkbookSheetSnapshot
  | HomeChatOfficePresentationSnapshot

export interface HomeChatOfficeEditorHandle {
  getSavePayload: () => HomeChatOfficeSavePayload
  resetDirtyState: () => void
}

export function normalizeSheetCells(cells: unknown[][] | undefined): unknown[][] {
  if (!Array.isArray(cells) || cells.length === 0) {
    return [[]]
  }

  const normalized = cells.map((row) => (Array.isArray(row) ? [...row] : []))
  while (normalized.length > 1 && normalized[normalized.length - 1].every((value) => value == null || value === '')) {
    normalized.pop()
  }
  return normalized
}
