import type { AttachmentData } from '@/api/endpoints/agent'
import { wireRecord, wireString, wireNullableString } from './harnessWireFields'

export function wireArtifact(value: unknown) {
  const raw = wireRecord(value)
  return raw ? {
    ...raw,
    absolute_path: wireNullableString(raw.absolute_path ?? raw.absolutePath),
    relative_path: wireNullableString(raw.relative_path ?? raw.relativePath),
    base_dir: wireNullableString(raw.base_dir ?? raw.baseDir),
  } : null
}

export function attachmentViews(values: readonly Record<string, unknown>[]): AttachmentData[] {
  return values.map(value => ({
    type: value.type === 'image' ? 'image' : 'file',
    url: wireString(value.url) || '',
    name: wireString(value.name), preview_url: wireString(value.preview_url),
  }))
}
