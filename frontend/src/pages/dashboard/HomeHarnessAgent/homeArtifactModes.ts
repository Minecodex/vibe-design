import type { HarnessConversationRead, HarnessSkillRead } from '@/api/endpoints/agent'

export type HomeArtifactMode = 'web' | 'document' | 'spreadsheet' | 'slides' | 'image' | 'video'

const LEGACY_MODE_MAP: Record<string, HomeArtifactMode> = {
  general: 'web',
  ppt: 'slides',
}

const LEGACY_ENTRY_SKILL_MODE_MAP: Record<string, HomeArtifactMode> = {
  docx: 'document',
  pptx: 'slides',
  xlsx: 'spreadsheet',
  web: 'web',
}

export function normalizeHomeArtifactMode(value: string | null | undefined): HomeArtifactMode {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) {
    return 'web'
  }
  if (normalized in LEGACY_MODE_MAP) {
    return LEGACY_MODE_MAP[normalized]
  }
  if (normalized === 'web' || normalized === 'document' || normalized === 'spreadsheet' || normalized === 'slides' || normalized === 'image' || normalized === 'video') {
    return normalized
  }
  return 'web'
}

export function homeSkillIdToArtifactMode(skillId: string | null | undefined): HomeArtifactMode {
  const normalized = String(skillId || '').trim()
  if (!normalized) {
    return 'web'
  }
  if (normalized in LEGACY_ENTRY_SKILL_MODE_MAP) {
    return LEGACY_ENTRY_SKILL_MODE_MAP[normalized]
  }
  return 'web'
}

export function resolveConversationArtifactMode(
  conversation: Pick<HarnessConversationRead, 'artifact_mode' | 'skill_id'> | null | undefined,
): HomeArtifactMode {
  if (!conversation) {
    return 'web'
  }
  if (conversation.artifact_mode) {
    return normalizeHomeArtifactMode(conversation.artifact_mode)
  }
  return homeSkillIdToArtifactMode(conversation.skill_id)
}

export function supportsDesignSystem(mode: HomeArtifactMode): boolean {
  return mode === 'web' || mode === 'document' || mode === 'slides'
}

export function isHomeVisibleSkill(skill: HarnessSkillRead): boolean {
  if (skill.capabilities?.phase_enabled === false) {
    return false
  }
  if (skill.capabilities?.selection_enabled === false) {
    return false
  }
  return skill.capabilities?.home_visible !== false
}

export function filterHomeVisibleSkills(skills: HarnessSkillRead[]): HarnessSkillRead[] {
  return skills.filter(isHomeVisibleSkill)
}

export function getModeEntrySkillCandidates(
  skills: HarnessSkillRead[],
  artifactMode: HomeArtifactMode,
): HarnessSkillRead[] {
  return skills.filter((skill) => isHomeVisibleSkill(skill) && skill.artifact_mode === artifactMode)
}
