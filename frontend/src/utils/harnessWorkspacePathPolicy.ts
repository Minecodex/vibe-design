export type HarnessWorkspacePathKind =
  | 'empty'
  | 'direct_url'
  | 'current_workspace'
  | 'bare_workspace'

export interface HarnessWorkspacePathClassification {
  kind: HarnessWorkspacePathKind
  raw: string
  normalized: string
  workspaceRelative: boolean
}

const WORKSPACE_ROOT_PREFIXES = [
  'references/inputs/',
  'references/sources/',
  'references/generated/',
  'file_versions/',
  'project/',
  'published/',
  'skill/',
]

export function isHarnessDirectAssetUrl(value: string): boolean {
  return (
    value.startsWith('http://')
    || value.startsWith('https://')
    || value.startsWith('data:')
    || value.startsWith('blob:')
    || value.startsWith('/')
  )
}

export function classifyHarnessWorkspacePath(filePath: string | null | undefined): HarnessWorkspacePathClassification {
  const raw = String(filePath || '').trim()
  if (!raw) {
    return {
      kind: 'empty',
      raw,
      normalized: '',
      workspaceRelative: false,
    }
  }

  let normalized = raw.replace(/\\/g, '/')
  if (/^sandbox:\/+/i.test(normalized)) {
    normalized = normalized.replace(/^sandbox:\/+/i, '')
  }

  normalized = normalized.replace(/^\/+/, '')
  if (normalized.startsWith('code/files/')) {
    normalized = normalized.slice('code/files/'.length)
  } else if (normalized.startsWith('files/')) {
    normalized = normalized.slice('files/'.length)
  }

  if (normalized.startsWith('assets/inputs/')) {
    normalized = `references/inputs/${normalized.slice('assets/inputs/'.length)}`
  } else if (normalized.startsWith('assets/references/')) {
    normalized = `references/generated/${normalized.slice('assets/references/'.length)}`
  }

  const leadingSlashWorkspacePath = raw.startsWith('/')
    && WORKSPACE_ROOT_PREFIXES.some((prefix) => normalized.startsWith(prefix))

  if (isHarnessDirectAssetUrl(raw) && !leadingSlashWorkspacePath) {
    return {
      kind: 'direct_url',
      raw,
      normalized: raw,
      workspaceRelative: false,
    }
  }

  const kind: HarnessWorkspacePathKind = WORKSPACE_ROOT_PREFIXES.some((prefix) => normalized.startsWith(prefix))
    ? 'current_workspace'
    : 'bare_workspace'

  return {
    kind,
    raw,
    normalized,
    workspaceRelative: Boolean(normalized),
  }
}

export function normalizeHarnessWorkspacePathByPolicy(filePath: string | null | undefined): string {
  return classifyHarnessWorkspacePath(filePath).normalized
}

export function normalizeWorkspaceAttachmentPathByPolicy(url: string | null | undefined): string | null {
  const classified = classifyHarnessWorkspacePath(url)
  if (!classified.workspaceRelative) {
    return null
  }
  return WORKSPACE_ROOT_PREFIXES.some((prefix) => classified.normalized.startsWith(prefix))
    ? classified.normalized
    : null
}
