import type { CanvasItem } from '@/api/endpoints/projects'

const DEFAULT_PROJECT_NAME = 'Untitled'
const DEFAULT_ITEM_NAME = 'item'
const FILENAME_SEPARATOR = '_'
const INVALID_FILENAME_PART_CHARS = /[<>:"/\\|?*\u0000-\u001F]/g
const KNOWN_MEDIA_EXTENSION = /\.(?:avif|bmp|gif|jpe?g|m4v|mkv|mov|mp4|png|svg|webm|webp)$/i
const WINDOWS_RESERVED_NAMES = new Set([
  'CON',
  'PRN',
  'AUX',
  'NUL',
  'COM1',
  'COM2',
  'COM3',
  'COM4',
  'COM5',
  'COM6',
  'COM7',
  'COM8',
  'COM9',
  'LPT1',
  'LPT2',
  'LPT3',
  'LPT4',
  'LPT5',
  'LPT6',
  'LPT7',
  'LPT8',
  'LPT9',
])

type ExportNameItem = Pick<CanvasItem, 'id' | 'type' | 'name' | 'groupId'>

interface BuildCanvasExportFilenameMapOptions {
  projectName?: string | null
  canvasItems: ExportNameItem[]
  targetItemIds: string[]
  exportItems: ExportNameItem[]
}

interface NormalizeFilenamePartOptions {
  stripMediaExtension?: boolean
}

function stripMediaExtension(value: string) {
  return value.replace(KNOWN_MEDIA_EXTENSION, '')
}

function cleanFilenamePart(value: string, options: NormalizeFilenamePartOptions = {}) {
  const withoutExtension = options.stripMediaExtension ? stripMediaExtension(value) : value
  return withoutExtension
    .replace(INVALID_FILENAME_PART_CHARS, FILENAME_SEPARATOR)
    .replace(/\s+/g, ' ')
    .replace(/_+/g, FILENAME_SEPARATOR)
    .trim()
    .replace(/[. ]+$/g, '')
}

export function normalizeCanvasExportFilenamePart(
  value: string | null | undefined,
  fallback: string,
  options: NormalizeFilenamePartOptions = {},
) {
  const cleaned = cleanFilenamePart(String(value || ''), options) || cleanFilenamePart(fallback, options) || DEFAULT_ITEM_NAME
  return WINDOWS_RESERVED_NAMES.has(cleaned.toUpperCase()) ? `${cleaned}${FILENAME_SEPARATOR}` : cleaned
}

function getItemFallbackName(item: ExportNameItem) {
  if (item.type === 'video' || item.type === 'video_generator') {
    return `video-${item.id}`
  }

  if (item.type === 'image' || item.type === 'image_generator') {
    return `image-${item.id}`
  }

  return `item-${item.id}`
}

function getUniqueFilenameBase(baseName: string, usedNames: Map<string, number>) {
  const usedCount = usedNames.get(baseName) || 0
  usedNames.set(baseName, usedCount + 1)
  return usedCount === 0 ? baseName : `${baseName}${FILENAME_SEPARATOR}${usedCount + 1}`
}

function getExportGroupIds(canvasItems: ExportNameItem[], targetItemIds: string[]) {
  const targetIdSet = new Set(targetItemIds)
  return new Set(
    canvasItems
      .filter((item) => item.type === 'group' && targetIdSet.has(item.id))
      .map((item) => item.id),
  )
}

function getGroupExportTotals(exportItems: ExportNameItem[], exportGroupIds: Set<string>) {
  const totals = new Map<string, number>()
  exportItems.forEach((item) => {
    const groupId = item.groupId
    if (!groupId || !exportGroupIds.has(groupId)) return
    totals.set(groupId, (totals.get(groupId) || 0) + 1)
  })
  return totals
}

export function buildCanvasExportFilenameMap({
  projectName,
  canvasItems,
  targetItemIds,
  exportItems,
}: BuildCanvasExportFilenameMapOptions) {
  const projectPart = normalizeCanvasExportFilenamePart(projectName, DEFAULT_PROJECT_NAME)
  const groupById = new Map(
    canvasItems
      .filter((item) => item.type === 'group')
      .map((item) => [item.id, item]),
  )
  const exportGroupIds = getExportGroupIds(canvasItems, targetItemIds)
  const groupTotals = getGroupExportTotals(exportItems, exportGroupIds)
  const groupCounters = new Map<string, number>()
  const usedNames = new Map<string, number>()
  const filenameByItemId = new Map<string, string>()

  exportItems.forEach((item) => {
    const exportGroupId = item.groupId && exportGroupIds.has(item.groupId) ? item.groupId : null
    if (exportGroupId) {
      const group = groupById.get(exportGroupId)
      const groupPart = normalizeCanvasExportFilenamePart(group?.name, `group-${exportGroupId}`)
      const nextIndex = (groupCounters.get(exportGroupId) || 0) + 1
      groupCounters.set(exportGroupId, nextIndex)

      const total = groupTotals.get(exportGroupId) || nextIndex
      const indexWidth = Math.max(2, String(total).length)
      const indexPart = String(nextIndex).padStart(indexWidth, '0')
      const baseName = [projectPart, groupPart, indexPart].join(FILENAME_SEPARATOR)
      filenameByItemId.set(item.id, getUniqueFilenameBase(baseName, usedNames))
      return
    }

    const itemPart = normalizeCanvasExportFilenamePart(
      item.name,
      getItemFallbackName(item),
      { stripMediaExtension: true },
    )
    const baseName = [projectPart, itemPart].join(FILENAME_SEPARATOR)
    filenameByItemId.set(item.id, getUniqueFilenameBase(baseName, usedNames))
  })

  return filenameByItemId
}
