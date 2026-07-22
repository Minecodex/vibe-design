import {
  Sparkles,
  FileText,
  Presentation,
  TableProperties,
  LayoutTemplate,
  Image as ImageIcon,
  Clapperboard,
} from 'lucide-react'
import type {
  HarnessSkillRead,
  OfficeSessionSnapshot,
  OpenWorkspaceOfficeSessionResponse,
  WorkbookPayload,
  WorkbookSnapshotSheet,
  WorkbookSnapshotPayload,
  WorkspaceFileRead,
} from '@/api/endpoints/agent'
import { inferHomeHarnessAttachmentKind } from './components/homeChatAttachmentKinds'
import type { HomeArtifactMode } from './homeArtifactModes'
import type { HomeChatFileTab } from './components/homeChatFileTabs'
import type {
  HomeChatOfficeSheetSnapshot,
  HomeChatOfficeWorkbookSheetDataSnapshot,
  HomeChatOfficeWorkbookSheetSnapshot,
} from './components/homeChatOfficeSnapshots'
import { loadExceljsWorkbook } from './components/exceljsWorkbookLoader'
import { exceljsToUniverSheetSnapshot } from './components/exceljsToUniverSheetSnapshot'

export type HomeOpenWorkspaceOfficeSessionResponse =
  Omit<OpenWorkspaceOfficeSessionResponse, 'snapshot'> & {
    snapshot?: OfficeSessionSnapshot | HomeChatOfficeSheetSnapshot | null
  }

export const SKILL_MODES: Array<{
  id: HomeArtifactMode
  icon: typeof Sparkles
  color: string
  bg: string
  bgLight: string
}> = [
  { id: 'web', icon: LayoutTemplate, color: 'text-blue-500', bg: 'bg-blue-500/10', bgLight: 'bg-blue-50' },
  { id: 'document', icon: FileText, color: 'text-indigo-500', bg: 'bg-indigo-500/10', bgLight: 'bg-indigo-50' },
  { id: 'spreadsheet', icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500/10', bgLight: 'bg-emerald-50' },
  { id: 'slides', icon: Presentation, color: 'text-rose-500', bg: 'bg-rose-500/10', bgLight: 'bg-rose-50' },
  { id: 'image', icon: ImageIcon, color: 'text-amber-500', bg: 'bg-amber-500/10', bgLight: 'bg-amber-50' },
  { id: 'video', icon: Clapperboard, color: 'text-violet-500', bg: 'bg-violet-500/10', bgLight: 'bg-violet-50' },
] as const

export function getHomeSkillModePresentation(mode: HomeArtifactMode) {
  return SKILL_MODES.find((entry) => entry.id === mode) || SKILL_MODES[0]
}

export function buildWorkspaceFileFromHarnessUpload(
  upload: { url: string; filename: string; type: string; size: number; asset_id?: string },
  fallbackName?: string,
): WorkspaceFileRead {
  const path = String(upload.url || '').trim()
  const name = String(upload.filename || fallbackName || path.split('/').pop() || 'attachment').trim()
  const inferredKind = inferHomeHarnessAttachmentKind({ name, path, type: upload.type })
  return {
    file_id: String(upload.asset_id || path || name || 'asset'),
    name,
    path,
    type: inferredKind,
    size: Number(upload.size || 0),
    created_at: new Date().toISOString(),
    updated_at: null,
    current_version_id: '',
    versions: [],
    source: 'input_asset',
  }
}

export function isChineseLanguage(language: string | null | undefined): boolean {
  return String(language || '').toLowerCase().startsWith('zh')
}

export function getLocalizedSkillName(skill: HarnessSkillRead | null | undefined, language: string): string {
  if (!skill) {
    return ''
  }
  if (isChineseLanguage(language)) {
    return skill.name_zh || skill.name || skill.name_en || skill.id
  }
  return skill.name_en || skill.name || skill.name_zh || skill.id
}

export function getLocalizedSkillDescription(skill: HarnessSkillRead | null | undefined, language: string): string {
  if (!skill) {
    return ''
  }
  if (isChineseLanguage(language)) {
    return skill.description_zh || skill.description || skill.description_en || ''
  }
  return skill.description_en || skill.description || skill.description_zh || ''
}

export function getConversationModeLabel(
  mode: HomeArtifactMode,
  translate: (key: string, fallback: string) => string,
): string {
  return translate(`home.modes.${mode}`, mode)
}

export function summarizeConversationRuntime(conv: {
  runtime_status?: string | null
  display_status?: string | null
  run_state?: string | null
  phase?: string | null
  activity?: string | null
  last_activity_source?: string | null
  last_tool?: string | null
}, translate: (key: string, fallback: string) => string, language: string): string {
  const displayStatus = String(conv.display_status || '').trim()
  const runtimeStatus = String(conv.runtime_status || '').toLowerCase()
  const runState = String(conv.run_state || conv.runtime_status || '').toLowerCase()
  const phase = String(conv.phase || '').toLowerCase()
  const activity = String(conv.activity || '').toLowerCase()
  const lastActivitySource = String(conv.last_activity_source || '').toLowerCase()
  const lastTool = String(conv.last_tool || '').toLowerCase()

  if (runtimeStatus === 'waiting_input' || runState === 'waiting_input') {
    return translate('home.runtime.status.waiting_input', 'Waiting for input')
  }
  if (runtimeStatus === 'completed' || runState === 'completed') {
    return translate('home.runtime.status.completed', 'Completed')
  }
  if (runtimeStatus === 'blocked' || runState === 'blocked' || runState === 'stalled') {
    return translate('home.runtime.status.blocked', 'Blocked')
  }
  if (runtimeStatus === 'failed' || runState === 'failed') {
    return lastActivitySource === 'engine_exception'
      ? (isChineseLanguage(language) ? '异常' : 'Exception')
      : translate('home.runtime.status.failed', 'Failed')
  }
  if (runtimeStatus === 'cancelled' || runState === 'cancelled') {
    return translate('home.runtime.status.cancelled', 'Cancelled')
  }
  if (runtimeStatus === 'running') {
    if (activity === 'planning_outline') {
      return translate('home.runtime.activity.planning_outline', 'Planning')
    }
    if (activity === 'searching' || lastTool === 'web_search' || lastTool === 'fetch_webpage') {
      return translate('home.runtime.activity.searching', 'Searching')
    }
    if (activity === 'analyzing') {
      return translate('home.runtime.activity.analyzing', 'Analyzing')
    }
    if (activity === 'skill_resolving') {
      return translate('home.runtime.activity.skill_resolving', 'Selecting skill')
    }
    if (activity === 'design_selecting') {
      return translate('home.runtime.activity.design_selecting', 'Selecting design')
    }
    if (activity === 'executing') {
      return translate('home.runtime.phaseValue.executing', 'Executing')
    }
    if (activity === 'answering') {
      return translate('home.runtime.activity.answering', 'Answering')
    }
    return translate('home.runtime.status.running', 'Running')
  }
  if (activity === 'planning_outline') {
    return translate('home.runtime.phaseValue.planning', 'Planning')
  }
  if (phase === 'planning_ready') {
    return translate('home.runtime.phaseValue.planning_ready', 'Ready')
  }
  if (phase === 'revising_plan') {
    return translate('home.runtime.phaseValue.revising_plan', 'Revising')
  }
  if (phase === 'executing') {
    return translate('home.runtime.phaseValue.executing', 'Executing')
  }
  if (displayStatus) {
    return displayStatus
  }
  return translate('home.runtime.status.idle', 'Idle')
}

export function getActivePreviewBaseFileVersion(
  file: SessionFileItem | null,
  versionId: string | null,
): { file_id: string; version_id: string; name: string } | null {
  if (!file?.file_id) {
    return null
  }
  const versions = file.versions || []
  if (versions.length <= 0) {
    return null
  }
  const selectedVersionId = versionId || file.current_version_id || versions[versions.length - 1]?.version_id
  if (!selectedVersionId) {
    return null
  }
  return {
    file_id: file.file_id,
    version_id: selectedVersionId,
    name: file.name,
  }
}

export function downloadWorkspaceBlob(blob: Blob, fileName: string) {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = fileName
  link.target = '_blank'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}

export function getAttachmentNameFromUrl(url: string) {
  const path = url.split('?')[0] || url
  const parts = path.split('/')
  return parts[parts.length - 1] || 'attachment'
}

export interface SessionFileItem extends WorkspaceFileRead {
  previewUrl?: string
  source: 'workspace' | 'generated' | 'versioned_file' | 'input_asset' | 'reference_asset' | 'plan_asset' | string
}

function isWorkspaceImageFile(file: WorkspaceFileRead) {
  const extension = String(file.name || file.path || '').split('.').pop()?.toLowerCase() || ''
  return file.type === 'image' || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(extension)
}

function isWorkspaceVideoFile(file: WorkspaceFileRead) {
  const extension = String(file.name || file.path || '').split('.').pop()?.toLowerCase() || ''
  return file.type === 'video' || ['mp4', 'webm', 'mov', 'm4v', 'avi'].includes(extension)
}

export function isSessionImageFile(file: SessionFileItem) {
  return isWorkspaceImageFile(file)
}

export function isSessionVideoFile(file: SessionFileItem) {
  return isWorkspaceVideoFile(file)
}

export function collectSessionFiles(
  workspaceFiles: WorkspaceFileRead[],
): SessionFileItem[] {
  const files = new Map<string, SessionFileItem>()

  for (const file of workspaceFiles) {
    files.set(`workspace:${file.path}`, {
      ...file,
      path: String(file.path || '').replace(/\\/g, '/'),
      source: file.source || 'workspace',
    })
  }

  return Array.from(files.values()).sort((a, b) => {
    const aIsPlan = String(a.path || a.name || '').toLowerCase().endsWith('plan.md')
    const bIsPlan = String(b.path || b.name || '').toLowerCase().endsWith('plan.md')
    if (aIsPlan !== bIsPlan) {
      return aIsPlan ? -1 : 1
    }
    return String(a.name || a.path || '').localeCompare(String(b.name || b.path || ''))
  })
}

export function getHomeFileTabFallback(tab: HomeChatFileTab): string {
  switch (tab) {
    case 'outputs':
      return 'Outputs'
    case 'inputs':
      return 'Uploads'
    case 'references':
      return 'References'
    case 'all':
    default:
      return 'All'
  }
}

function mergeSheetSnapshotWarnings(
  snapshot: HomeChatOfficeWorkbookSheetSnapshot,
  warnings: string[] | undefined,
): HomeChatOfficeWorkbookSheetSnapshot {
  const mergedWarning = (warnings || []).map((warning) => String(warning || '').trim()).filter(Boolean).join('\n')
  if (!mergedWarning) {
    return snapshot
  }

  return {
    ...snapshot,
    warning: snapshot.warning ? `${snapshot.warning}\n${mergedWarning}` : mergedWarning,
  }
}

export function isHomeChatOfficeSheetSnapshot(
  snapshot: OfficeSessionSnapshot | HomeChatOfficeSheetSnapshot | null | undefined,
): snapshot is HomeChatOfficeSheetSnapshot {
  return Boolean(
    snapshot
    && snapshot.kind === 'sheet'
    && (
      Array.isArray((snapshot as HomeChatOfficeSheetSnapshot).sheets)
      || Array.isArray((snapshot as HomeChatOfficeWorkbookSheetSnapshot).sheetOrder)
    )
  )
}

function isWorkbookSnapshotPayload(
  snapshot: OfficeSessionSnapshot | null | undefined,
): snapshot is WorkbookSnapshotPayload {
  return Boolean(
    snapshot
    && snapshot.kind === 'sheet'
    && Array.isArray((snapshot as WorkbookSnapshotPayload).sheetOrder)
    && !Array.isArray((snapshot as WorkbookSnapshotPayload).sheets),
  )
}

function isWorkbookPayload(
  snapshot: OfficeSessionSnapshot | null | undefined,
): snapshot is WorkbookPayload {
  return Boolean(
    snapshot
    && snapshot.kind === 'sheet'
    && Array.isArray((snapshot as WorkbookPayload).sheets),
  )
}

function mergeWorkbookWarning<T extends { warning?: string | null }>(
  snapshot: T,
  warnings: string[] | undefined,
): T {
  const mergedWarning = (warnings || []).map((warning) => String(warning || '').trim()).filter(Boolean).join('\n')
  if (!mergedWarning) {
    return snapshot
  }

  return {
    ...snapshot,
    warning: snapshot.warning ? `${snapshot.warning}\n${mergedWarning}` : mergedWarning,
  }
}

function normalizeWorkbookRowHeights(
  rows: Record<string, Record<string, any>> | null | undefined,
): Record<string, { h: number }> {
  return Object.entries(rows || {}).reduce<Record<string, { h: number }>>((accumulator, [rowIndex, row]) => {
    if (row && typeof row === 'object' && typeof (row as { h?: unknown }).h === 'number') {
      accumulator[rowIndex] = { h: (row as { h: number }).h }
    }
    return accumulator
  }, {})
}

function normalizeWorkbookColumnWidths(
  cols: Record<string, Record<string, any>> | null | undefined,
): Record<string, { w: number }> {
  return Object.entries(cols || {}).reduce<Record<string, { w: number }>>((accumulator, [columnIndex, column]) => {
    if (column && typeof column === 'object' && typeof (column as { w?: unknown }).w === 'number') {
      accumulator[columnIndex] = { w: (column as { w: number }).w }
    }
    return accumulator
  }, {})
}

function normalizeWorkbookSheetData(
  sheet: WorkbookSnapshotSheet | WorkbookPayload['sheets'][number],
  fallbackId: string,
): HomeChatOfficeWorkbookSheetDataSnapshot {
  const sheetId = String(sheet.id || fallbackId)
  return {
    id: sheetId,
    name: String(sheet.name || fallbackId),
    rows: normalizeWorkbookRowHeights(sheet.rows),
    cols: normalizeWorkbookColumnWidths(sheet.cols),
    cells: sheet.cells || {},
    merges: sheet.merges || [],
    freeze: sheet.freeze || null,
  }
}

function normalizeWorkbookStyles(
  styles: Record<string, Record<string, any>> | null | undefined,
): Record<string, Record<string, unknown>> {
  return Object.entries(styles || {}).reduce<Record<string, Record<string, unknown>>>((accumulator, [styleId, style]) => {
    if (style && typeof style === 'object') {
      accumulator[styleId] = style as Record<string, unknown>
    }
    return accumulator
  }, {})
}

function normalizeWorkbookPayloadSnapshot(
  snapshot: WorkbookPayload,
): HomeChatOfficeWorkbookSheetSnapshot {
  const normalizedSheets = (snapshot.sheets || []).reduce<HomeChatOfficeWorkbookSheetSnapshot['sheets']>((accumulator, sheet, index) => {
    const fallbackId = `sheet-${index + 1}`
    const normalizedSheet = normalizeWorkbookSheetData(sheet, fallbackId)
    accumulator[normalizedSheet.id] = normalizedSheet
    return accumulator
  }, {})

  const sheetOrder = Object.keys(normalizedSheets)
  return {
    kind: 'sheet',
    sheetOrder,
    activeSheetId: sheetOrder[0] || 'sheet-1',
    sheets: normalizedSheets,
    styles: normalizeWorkbookStyles(snapshot.styles),
  }
}

function normalizeSheetSnapshot(
  snapshot: OfficeSessionSnapshot | null | undefined,
  warnings: string[] | undefined,
): HomeChatOfficeSheetSnapshot | null {
  if (isWorkbookSnapshotPayload(snapshot)) {
    const normalizedSnapshot: HomeChatOfficeWorkbookSheetSnapshot = {
      kind: 'sheet',
      sheetOrder: snapshot.sheetOrder || [],
      activeSheetId: snapshot.activeSheetId || snapshot.sheetOrder?.[0] || 'sheet-1',
      sheets: Object.entries(snapshot.sheets || {}).reduce<HomeChatOfficeWorkbookSheetSnapshot['sheets']>((accumulator, [sheetId, sheet]) => {
        accumulator[sheetId] = normalizeWorkbookSheetData(sheet, sheetId)
        return accumulator
      }, {}),
      styles: normalizeWorkbookStyles(snapshot.styles),
      ...(snapshot.warning ? { warning: snapshot.warning } : {}),
    }
    return mergeSheetSnapshotWarnings(normalizedSnapshot, warnings)
  }

  if (isWorkbookPayload(snapshot)) {
    return mergeWorkbookWarning(normalizeWorkbookPayloadSnapshot(snapshot), warnings)
  }

  if (isHomeChatOfficeSheetSnapshot(snapshot)) {
    return mergeSheetSnapshotWarnings(snapshot, warnings)
  }

  return null
}

export async function buildSheetOfficeSessionSnapshot(
  session: OpenWorkspaceOfficeSessionResponse,
  fileName: string | undefined,
): Promise<HomeOpenWorkspaceOfficeSessionResponse> {
  if (session.file_kind !== 'sheet' || !session.source_blob || session.preview_file_path) {
    return session
  }

  const fallbackSnapshot = normalizeSheetSnapshot(session.snapshot, session.warnings)

  try {
    const workbook = await loadExceljsWorkbook({
      base64: session.source_blob,
      mimeType: session.source_mime_type,
      fileName: fileName || session.file_path,
    })

    return {
      ...session,
      snapshot: mergeSheetSnapshotWarnings(
        exceljsToUniverSheetSnapshot(workbook),
        session.warnings,
      ),
    }
  } catch (error) {
    if (fallbackSnapshot) {
      return {
        ...session,
        snapshot: fallbackSnapshot,
      }
    }
    throw error
  }
}


