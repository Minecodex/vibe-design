import type { ComponentType, ReactNode } from 'react'
import type { ProjectionMessageBlock } from './types'

export interface PresentationBlockRendererProps<TBlock extends ProjectionMessageBlock = ProjectionMessageBlock> {
  block: TBlock
  children?: ReactNode
}

export type PresentationBlockRenderer<TBlock extends ProjectionMessageBlock = ProjectionMessageBlock> =
  ComponentType<PresentationBlockRendererProps<TBlock> & Record<string, unknown>>

export type PresentationRendererRegistry = Readonly<Record<string, PresentationBlockRenderer>>

export interface MutablePresentationRendererRegistry {
  register(uiKind: string, renderer: PresentationBlockRenderer): void
  registerMany(renderers: Record<string, PresentationBlockRenderer>): void
  resolve(uiKind: string | null | undefined): PresentationBlockRenderer | null
  has(uiKind: string | null | undefined): boolean
  snapshot(): PresentationRendererRegistry
}

export const DEFAULT_PRESENTATION_UI_KINDS = [
  'text',
  'tool_call',
  'tool_result',
  'subagent_card',
  'interaction_form',
  'plan_card',
  'progress_card',
  'artifact_card',
  'error_card',
] as const

export type DefaultPresentationUiKind = typeof DEFAULT_PRESENTATION_UI_KINDS[number]

const UI_KIND_ALIASES: Record<string, DefaultPresentationUiKind> = {
  assistant_text: 'text',
  assistant_final_answer: 'text',
  compact_tool: 'tool_call',
  stream_panel: 'tool_result',
  user_plan_card: 'plan_card',
  planning_draft_card: 'plan_card',
  plan_artifact: 'plan_card',
  progress_update: 'progress_card',
  user_progress_card: 'progress_card',
  generation_task: 'artifact_card',
  generation_card: 'artifact_card',
  media_card: 'artifact_card',
  user_artifact_card: 'artifact_card',
  choice_prompt: 'interaction_form',
}

export function normalizePresentationUiKind(uiKind: string | null | undefined): string {
  const normalized = String(uiKind || '').trim()
  if (!normalized) {
    return 'text'
  }
  return UI_KIND_ALIASES[normalized] ?? normalized
}

export function createPresentationRendererRegistry(
  initialRenderers: Record<string, PresentationBlockRenderer> = {},
): MutablePresentationRendererRegistry {
  const renderers: Record<string, PresentationBlockRenderer> = {}

  const register = (uiKind: string, renderer: PresentationBlockRenderer) => {
    const normalized = normalizePresentationUiKind(uiKind)
    renderers[normalized] = renderer
  }

  Object.entries(initialRenderers).forEach(([uiKind, renderer]) => register(uiKind, renderer))

  return {
    register,
    registerMany(nextRenderers) {
      Object.entries(nextRenderers).forEach(([uiKind, renderer]) => register(uiKind, renderer))
    },
    resolve(uiKind) {
      return renderers[normalizePresentationUiKind(uiKind)] ?? null
    },
    has(uiKind) {
      return Boolean(renderers[normalizePresentationUiKind(uiKind)])
    },
    snapshot() {
      return { ...renderers }
    },
  }
}

export function assertDefaultPresentationRenderers(
  registry: Pick<MutablePresentationRendererRegistry, 'has'>,
): void {
  const missing = DEFAULT_PRESENTATION_UI_KINDS.filter((uiKind) => !registry.has(uiKind))
  if (missing.length > 0) {
    throw new Error(`Missing presentation renderers: ${missing.join(', ')}`)
  }
}

export function registerDefaultPresentationRenderers(
  registry: Pick<MutablePresentationRendererRegistry, 'register'>,
  renderer: PresentationBlockRenderer,
): void {
  DEFAULT_PRESENTATION_UI_KINDS.forEach((uiKind) => registry.register(uiKind, renderer))
}
