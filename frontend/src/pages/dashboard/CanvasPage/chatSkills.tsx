import type { LucideIcon } from 'lucide-react'
import { Image, Palette, Sparkles, SwatchBook, Target } from 'lucide-react'
import type { HarnessSkillRead } from '@/api/endpoints/agent'
import type { ChatUiConfig } from '@/store/canvasAgentTypes'
import { FALLBACK_CANVAS_EXPLICIT_SKILL_IDS, normalizeCanvasSkillIdAlias } from '@/store/canvasAgentTypes'

export type ChatSkillId = string

export interface ChatSkillDefinition {
  id: ChatSkillId
  color: string
  icon: LucideIcon
  nameKey: string
  defaultName: string
}

export const CHAT_SKILLS: ChatSkillDefinition[] = [
  {
    id: 'brand_strategy_architect',
    color: 'var(--app-primary)',
    icon: Target,
    nameKey: 'canvas.chat.skills.brand_strategy_architect',
    defaultName: '品牌策划方案',
  },
  {
    id: 'logo',
    color: 'var(--app-warning)',
    icon: Palette,
    nameKey: 'canvas.chat.skills.logo',
    defaultName: 'Logo 设计',
  },
  {
    id: 'menswear-ecommerce-hero',
    color: 'var(--app-warning)',
    icon: Image,
    nameKey: 'canvas.chat.skills.menswear-ecommerce-hero',
    defaultName: '男装电商图',
  },
  {
    id: 'vi-design-guide',
    color: 'var(--app-primary)',
    icon: SwatchBook,
    nameKey: 'canvas.chat.skills.vi-design-guide',
    defaultName: 'VI 设计指南',
  },
]

export const CHAT_SKILL_META = Object.fromEntries(
  CHAT_SKILLS.map((skill) => [skill.id, skill])
) as Record<string, ChatSkillDefinition>

const ICON_BY_NAME: Record<string, LucideIcon> = {
  image: Image,
  palette: Palette,
  sparkles: Sparkles,
  swatchbook: SwatchBook,
  target: Target,
}

function resolveSkillIcon(skill: HarnessSkillRead | null | undefined, fallback?: ChatSkillDefinition): LucideIcon {
  const normalizedIcon = String(skill?.icon || '').trim().toLowerCase()
  return ICON_BY_NAME[normalizedIcon] || fallback?.icon || Sparkles
}

function resolveSkillColor(skill: HarnessSkillRead | null | undefined, fallback?: ChatSkillDefinition): string {
  const color = String(skill?.color || '').trim()
  return color || fallback?.color || 'var(--app-primary)'
}

function isChineseLanguage(language: string | null | undefined): boolean {
  return String(language || '').toLowerCase().startsWith('zh')
}

function getLocalizedCanvasSkillName(skill: HarnessSkillRead, language: string): string {
  if (isChineseLanguage(language)) {
    return skill.name_zh || skill.name || skill.name_en || skill.id
  }
  return skill.name_en || skill.name || skill.name_zh || skill.id
}

export function buildCanvasChatSkills(
  uiConfig: ChatUiConfig | null | undefined,
  language: string,
  translate: (key: string, fallback: string) => string,
): Array<ChatSkillDefinition & { name: string }> {
  const skillById = new Map((uiConfig?.canvasSkills || []).map(skill => [normalizeCanvasSkillIdAlias(skill.id), skill]))
  const configuredIds = uiConfig?.canvasExplicitSkillIds?.length
    ? uiConfig.canvasExplicitSkillIds
    : FALLBACK_CANVAS_EXPLICIT_SKILL_IDS
  const ids = Array.from(
    new Set(
      configuredIds
        .map(normalizeCanvasSkillIdAlias)
        .filter(Boolean),
    ),
  )

  return ids.map((id) => {
    const fallback = CHAT_SKILL_META[id]
    const catalogSkill = skillById.get(id)
    const defaultName = fallback?.defaultName || catalogSkill?.name || id
    return {
      id,
      color: resolveSkillColor(catalogSkill, fallback),
      icon: resolveSkillIcon(catalogSkill, fallback),
      nameKey: fallback?.nameKey || `canvas.chat.skills.${id}`,
      defaultName,
      name: fallback
        ? translate(fallback.nameKey, fallback.defaultName)
        : catalogSkill
          ? getLocalizedCanvasSkillName(catalogSkill, language)
          : translate(`canvas.chat.skills.${id}`, defaultName),
    }
  })
}
