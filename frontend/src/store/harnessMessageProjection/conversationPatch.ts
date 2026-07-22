import type { HarnessConversationRead } from '@/api/endpoints/agent'
import type { PresentationOpEvent } from './types'

export type PresentationConversationPatch = Partial<Pick<
  HarnessConversationRead,
  | 'skill_id'
  | 'resolved_skill_id'
  | 'skill_selection_mode'
  | 'skill_resolution_source'
  | 'artifact_mode'
  | 'design_system_id'
  | 'last_skill_decision_reason'
  | 'last_skill_decision_confidence'
  | 'phase'
>>

export function extractPresentationConversationPatch(
  event: PresentationOpEvent | null | undefined,
): PresentationConversationPatch | null {
  if (event?.type !== 'presentation.conversation.patch') {
    return null
  }
  const data = event.data && typeof event.data === 'object'
    ? event.data
    : event.payload && typeof event.payload === 'object'
      ? event.payload
      : {}
  const payload = data.payload && typeof data.payload === 'object'
    ? data.payload as Record<string, unknown>
    : {}
  const patchSource = payload.patch && typeof payload.patch === 'object'
    ? payload.patch as Record<string, unknown>
    : payload
  const patch: PresentationConversationPatch = {}
  copyString(patch, patchSource, 'skill_id')
  copyString(patch, patchSource, 'resolved_skill_id')
  copyString(patch, patchSource, 'skill_selection_mode')
  copyString(patch, patchSource, 'skill_resolution_source')
  copyString(patch, patchSource, 'artifact_mode')
  copyString(patch, patchSource, 'design_system_id')
  copyString(patch, patchSource, 'last_skill_decision_reason')
  copyNumber(patch, patchSource, 'last_skill_decision_confidence')
  copyString(patch, patchSource, 'phase')
  return Object.keys(patch).length > 0 ? patch : null
}

export function applyPresentationConversationPatchToMeta(
  conversation: HarnessConversationRead,
  patch: PresentationConversationPatch | null,
): HarnessConversationRead {
  if (!patch) {
    return conversation
  }
  return {
    ...conversation,
    ...patch,
    skill_selection_mode: patch.skill_selection_mode === 'manual' ? 'manual' : patch.skill_selection_mode === 'auto' ? 'auto' : conversation.skill_selection_mode,
    updated_at: new Date().toISOString(),
  } as HarnessConversationRead
}

export function hasPresentationSkillPatch(patch: PresentationConversationPatch | null | undefined): boolean {
  return Boolean(
    patch
    && (
      Object.prototype.hasOwnProperty.call(patch, 'skill_id')
      || Object.prototype.hasOwnProperty.call(patch, 'resolved_skill_id')
      || Object.prototype.hasOwnProperty.call(patch, 'skill_selection_mode')
      || Object.prototype.hasOwnProperty.call(patch, 'last_skill_decision_reason')
      || Object.prototype.hasOwnProperty.call(patch, 'last_skill_decision_confidence')
    ),
  )
}

function copyString(target: Record<string, unknown>, source: Record<string, unknown>, key: string): void {
  if (!(key in source)) {
    return
  }
  const value = source[key]
  target[key] = value == null ? null : String(value)
}

function copyNumber(target: Record<string, unknown>, source: Record<string, unknown>, key: string): void {
  if (!(key in source)) {
    return
  }
  const value = source[key]
  const parsed = Number(value)
  target[key] = Number.isFinite(parsed) ? parsed : null
}
