import { describe, expect, it } from 'vitest'

import type { HarnessSkillRead } from '@/api/endpoints/agent'

import {
  filterHomeVisibleSkills,
  getModeEntrySkillCandidates,
  homeSkillIdToArtifactMode,
  isHomeVisibleSkill,
  normalizeHomeArtifactMode,
  resolveConversationArtifactMode,
  supportsDesignSystem,
} from './homeArtifactModes'

function buildSkill(overrides: Partial<HarnessSkillRead>): HarnessSkillRead {
  return {
    id: 'web',
    name: 'Web',
    name_en: 'Web',
    description: '',
    color: 'blue',
    icon: 'sparkles',
    triggers: [],
    mode: 'prototype',
    surface: 'web',
    platform: 'desktop',
    scenario: 'general',
    artifact_mode: 'web',
    default_for: [],
    featured: null,
    preview_type: 'html',
    preview_entry: null,
    protocol_provider: 'open_design',
    protocol_family: 'open_design_free_web',
    protocol_metadata: {},
    capabilities: {},
    example_prompt: null,
    ...overrides,
  }
}

describe('homeArtifactModes', () => {
  it('normalizes legacy and current modes', () => {
    expect(normalizeHomeArtifactMode('ppt')).toBe('slides')
    expect(normalizeHomeArtifactMode('general')).toBe('web')
    expect(normalizeHomeArtifactMode('image')).toBe('image')
    expect(normalizeHomeArtifactMode(undefined)).toBe('web')
  })

  it('maps only legacy entry skills when conversation artifact mode is missing', () => {
    expect(homeSkillIdToArtifactMode('docx')).toBe('document')
    expect(homeSkillIdToArtifactMode('pptx')).toBe('slides')
    expect(homeSkillIdToArtifactMode('xlsx')).toBe('spreadsheet')
    expect(homeSkillIdToArtifactMode('web')).toBe('web')
    expect(homeSkillIdToArtifactMode('image-poster')).toBe('web')
    expect(homeSkillIdToArtifactMode('video-shortform')).toBe('web')
    expect(homeSkillIdToArtifactMode('hatch-pet')).toBe('web')
    expect(homeSkillIdToArtifactMode('unknown-skill')).toBe('web')
  })

  it('prefers explicit conversation artifact mode', () => {
    expect(resolveConversationArtifactMode({ artifact_mode: 'image', skill_id: 'docx' })).toBe('image')
    expect(resolveConversationArtifactMode({ artifact_mode: undefined, skill_id: 'pptx' })).toBe('slides')
  })

  it('marks the design-system eligible modes', () => {
    expect(supportsDesignSystem('web')).toBe(true)
    expect(supportsDesignSystem('document')).toBe(true)
    expect(supportsDesignSystem('slides')).toBe(true)
    expect(supportsDesignSystem('video')).toBe(false)
  })

  it('returns all skills in the active mode', () => {
    const skills = [
      buildSkill({ id: 'web', artifact_mode: 'web' }),
      buildSkill({ id: 'pricing-page', artifact_mode: 'web' }),
      buildSkill({ id: 'pptx', artifact_mode: 'slides' }),
    ]

    expect(getModeEntrySkillCandidates(skills, 'web').map((skill) => skill.id)).toEqual(['web', 'pricing-page'])
    expect(getModeEntrySkillCandidates(skills, 'slides').map((skill) => skill.id)).toEqual(['pptx'])
  })

  it('hides canvas-only skills from home mode listings', () => {
    const skills = [
      buildSkill({ id: 'image-poster', artifact_mode: 'image' }),
      buildSkill({ id: 'design_workflow', artifact_mode: 'image', capabilities: { home_visible: false } }),
      buildSkill({ id: 'logo', artifact_mode: 'image', capabilities: { home_visible: false } }),
    ]

    expect(isHomeVisibleSkill(skills[0])).toBe(true)
    expect(isHomeVisibleSkill(skills[1])).toBe(false)
    expect(filterHomeVisibleSkills(skills).map((skill) => skill.id)).toEqual(['image-poster'])
    expect(getModeEntrySkillCandidates(skills, 'image').map((skill) => skill.id)).toEqual(['image-poster'])
  })

  it('hides disabled or non-selectable skills from home mode listings', () => {
    const skills = [
      buildSkill({ id: 'html-ppt', artifact_mode: 'slides', capabilities: { home_visible: true, selection_enabled: true, phase_enabled: true } }),
      buildSkill({ id: 'open-design-landing-deck', artifact_mode: 'slides', capabilities: { home_visible: false, selection_enabled: false, phase_enabled: false } }),
      buildSkill({ id: 'critique', artifact_mode: 'slides', capabilities: { home_visible: false, selection_enabled: false, phase_enabled: true } }),
    ]

    expect(filterHomeVisibleSkills(skills).map((skill) => skill.id)).toEqual(['html-ppt'])
    expect(getModeEntrySkillCandidates(skills, 'slides').map((skill) => skill.id)).toEqual(['html-ppt'])
  })
})
