import { wireRecord, wireString, wireNullableString } from './harnessWireFields'
import type { WorkspaceFileRead, WorkspaceFileVersionRead } from '@/api/endpoints/agent'

function normalizeVersion(raw: Record<string, unknown>): WorkspaceFileVersionRead {
  return {
    version_id: String(raw.version_id || raw.versionId || ''),
    label: String(raw.label || ''),
    size: Number(raw.size || 0),
    sha256: String(raw.sha256 || ''),
    created_at: String(raw.created_at || raw.createdAt || ''),
    created_by: String(raw.created_by || raw.createdBy || 'agent'),
    run_id: wireNullableString(raw.run_id ?? raw.runId ?? null),
    parent_version_id: wireNullableString(raw.parent_version_id ?? raw.parentVersionId ?? null),
    parent_input_asset_ids: Array.isArray(raw.parent_input_asset_ids) ? raw.parent_input_asset_ids.map(String) : [],
    referenced_asset_ids: Array.isArray(raw.referenced_asset_ids) ? raw.referenced_asset_ids.map(String) : [],
    note: wireNullableString(raw.note ?? null),
    artifact_metadata: wireRecord(raw.artifact_metadata) ?? wireRecord(raw.artifactMetadata),
  }
}

export function normalizeVersionedFile(raw: Record<string, unknown>): WorkspaceFileRead {
  const versionsSource = Array.isArray(raw.versions) ? raw.versions : []
  const versions = versionsSource.flatMap((item) => {
    const record = wireRecord(item)
    return record ? [normalizeVersion(record)] : []
  })
  const versionSource = wireRecord(raw.current_version) ?? wireRecord(raw.version)
  const version = versionSource ? normalizeVersion(versionSource) : null
  const mergedVersions = version && !versions.some((item) => item.version_id === version.version_id)
    ? [...versions, version]
    : versions

  return {
    file_id: String(raw.file_id || raw.fileId || raw.path || raw.file_path || ''),
    name: String(raw.name || raw.file_name || wireString(raw.file_path)?.split('/').pop() || ''),
    path: String(raw.path || raw.file_path || ''),
    type: String(raw.type || 'other'),
    size: Number(raw.size || version?.size || 0),
    created_at: String(raw.created_at || raw.createdAt || version?.created_at || ''),
    updated_at: wireNullableString(raw.updated_at ?? raw.updatedAt ?? raw.created_at ?? null),
    current_version_id: String(raw.current_version_id || raw.currentVersionId || version?.version_id || ''),
    current_version_path: wireNullableString(raw.current_version_path ?? raw.currentVersionPath ?? raw.path ?? raw.file_path ?? null),
    artifact_kind: wireNullableString(raw.artifact_kind ?? raw.artifactKind ?? version?.artifact_metadata?.artifact_kind ?? null),
    artifact_metadata: wireRecord(raw.artifact_metadata) ?? wireRecord(raw.artifactMetadata) ?? version?.artifact_metadata ?? null,
    versions: mergedVersions,
    source: wireString(raw.source ?? raw.category) ?? 'versioned_file',
  }
}

export function upsertVersionedFile(
  files: WorkspaceFileRead[],
  raw: Record<string, unknown>,
): WorkspaceFileRead[] {
  const next = normalizeVersionedFile(raw)
  if (!next.file_id && !next.path) {
    return files
  }
  const existing = files.findIndex((file) =>
    (next.file_id && file.file_id === next.file_id) || (next.path && file.path === next.path),
  )
  if (existing < 0) {
    return [...files, next]
  }
  const mergedVersions = [...(files[existing].versions || [])]
  for (const version of next.versions || []) {
    const versionIndex = mergedVersions.findIndex((item) => item.version_id === version.version_id)
    if (versionIndex >= 0) {
      mergedVersions[versionIndex] = version
    } else {
      mergedVersions.push(version)
    }
  }
  const output = [...files]
  const previous = files[existing]
  output[existing] = {
    ...previous,
    ...next,
    name: next.name || previous.name,
    path: next.path || previous.path,
    type: next.type === 'other' && !raw.type ? previous.type : next.type,
    size: next.size || previous.size,
    created_at: next.created_at || previous.created_at,
    updated_at: wireNullableString(next.updated_at ?? previous.updated_at),
    current_version_id: next.current_version_id || previous.current_version_id,
    current_version_path: wireNullableString(next.current_version_path ?? previous.current_version_path ?? null),
    artifact_kind: wireNullableString(next.artifact_kind ?? previous.artifact_kind ?? null),
    artifact_metadata: next.artifact_metadata ?? previous.artifact_metadata ?? null,
    source: next.source ?? previous.source,
    versions: mergedVersions,
  }
  return output
}

export function getSelectedFileVersion(file: WorkspaceFileRead, versionId?: string | null) {
  const target = versionId || file.current_version_id
  const versions = file.versions || []
  return versions.find((version) => version.version_id === target) || versions[versions.length - 1] || null
}

export function getVersionIndex(file: WorkspaceFileRead, versionId?: string | null): number {
  const selected = getSelectedFileVersion(file, versionId)
  if (!selected) {
    return -1
  }
  return (file.versions || []).findIndex((version) => version.version_id === selected.version_id)
}
