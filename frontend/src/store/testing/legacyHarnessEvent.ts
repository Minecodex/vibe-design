import type { AgentEvent } from '@/api/endpoints/agent'

type RetiredWireTag = 'message_done' | 'message_appended' | 'interaction_submitted'

/** Deliberately invalid legacy tags exercise replay and terminal-state guards. */
export function legacyHarnessEvent(event: Omit<AgentEvent, 'type'> & { type: RetiredWireTag }): AgentEvent {
  return event as unknown as AgentEvent
}
