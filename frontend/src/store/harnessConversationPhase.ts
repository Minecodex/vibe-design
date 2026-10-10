import type { HarnessConversationRead } from '@/api/endpoints/agent'

const phases = new Set<unknown>([
  'skill_resolving', 'discovery', 'visual_lock', 'planning', 'planning_ready',
  'awaiting_plan_review', 'revising_plan', 'executing', 'completed', 'failed', 'blocked',
] satisfies HarnessConversationRead['phase'][])

export function isHarnessConversationPhase(value: unknown): value is HarnessConversationRead['phase'] {
  return phases.has(value)
}
