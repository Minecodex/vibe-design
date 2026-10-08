import type { ChatMessage as CanvasChatMessage, MessageBlock as CanvasMessageBlock } from '../canvasAgentTypes'
import type { OutlineRuntimeRead, PlanningDraftRead, UserPlanRead } from '@/api/endpoints/agent'

export type ProjectionChatMessage = CanvasChatMessage
export type ProjectionMessageBlock = CanvasMessageBlock

export interface PresentationOpEvent {
  type: string
  sequence?: number
  source_sequence?: number
  op_id?: string
  run_id?: string | null
  data?: Record<string, unknown>
  payload?: Record<string, unknown>
}

export interface ProjectionSessionLike {
  messages: ProjectionChatMessage[]
  streamingBlocks: ProjectionMessageBlock[]
  lastSequence: number
  appliedPresentationOps?: string[]
  planningDraft?: PlanningDraftRead | null
  activeUserPlan?: UserPlanRead | null
  outlineRuntime?: OutlineRuntimeRead | null
  runtimeState?: Record<string, any> | null
}
