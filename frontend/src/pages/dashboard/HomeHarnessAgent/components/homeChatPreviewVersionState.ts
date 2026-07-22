import type { WorkspaceFileRead } from '@/api/endpoints/agent'

function sameWorkspaceFile(a: WorkspaceFileRead, b: WorkspaceFileRead): boolean {
  return Boolean(a.file_id && b.file_id && a.file_id === b.file_id)
    || Boolean(a.path && b.path && a.path === b.path)
}

export function findUpdatedPreviewFile(
  previewingFile: WorkspaceFileRead | null,
  workspaceFiles: WorkspaceFileRead[],
): WorkspaceFileRead | null {
  if (!previewingFile) {
    return null
  }
  return workspaceFiles.find((file) => sameWorkspaceFile(previewingFile, file)) || null
}

export function shouldResetPreviewVersionSelection(
  previousFile: WorkspaceFileRead | null,
  nextFile: WorkspaceFileRead | null,
  selectedVersionId: string | null,
): boolean {
  if (!previousFile || !nextFile || !selectedVersionId) {
    return false
  }
  const previousVersions = previousFile.versions || []
  const nextVersions = nextFile.versions || []
  const previousCurrent = previousFile.current_version_id || previousVersions[previousVersions.length - 1]?.version_id || ''
  const nextCurrent = nextFile.current_version_id || nextVersions[nextVersions.length - 1]?.version_id || ''
  return Boolean(previousCurrent && nextCurrent && previousCurrent !== nextCurrent)
}

export function findRuntimePreviewFile(
  runtimeEntryPath: string | null | undefined,
  workspaceFiles: WorkspaceFileRead[],
): WorkspaceFileRead | null {
  const normalizedEntryPath = String(runtimeEntryPath || '').replace(/\\/g, '/').replace(/^\/+/, '').trim()
  if (!normalizedEntryPath) {
    return null
  }
  return workspaceFiles.find((file) => {
    const normalizedPath = String(file.path || '').replace(/\\/g, '/').replace(/^\/+/, '').trim()
    return normalizedPath === normalizedEntryPath || normalizedPath === `project/${normalizedEntryPath}`
  }) || null
}
