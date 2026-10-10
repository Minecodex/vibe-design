import type { WorkspaceFileRead } from '@/api/endpoints/agent'

export function normalizeLegacyWorkspaceFileEvent(data: Record<string, unknown>): WorkspaceFileRead | null {
  const path = data.file_path
  if (typeof path !== 'string' || path.length === 0) return null
  const size = Number(data.size)
  return {
    name: path.split('/').pop() || '',
    path,
    type: typeof data.type === 'string' && data.type ? data.type : 'other',
    size: Number.isFinite(size) && size >= 0 ? size : 0,
    created_at: new Date().toISOString(),
  }
}
