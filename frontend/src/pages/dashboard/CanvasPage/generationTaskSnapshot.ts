import { agentApi } from '@/api/endpoints/agent'
import { generationApi, type GenerationTaskRead } from '@/api/endpoints/generation'

export type CanvasGenerationTaskSnapshot = Partial<GenerationTaskRead> & {
  task_id?: string | number
  artifact_ref?: string | null
  provider_code?: string | null
  prompt?: string | null
  resolution?: string | null
  duration?: string | number | null
  quality?: string | null
  result_urls?: string[] | null
  canvas_item?: Record<string, unknown> | null
  artifact?: Record<string, unknown> | null
  params?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export async function fetchCanvasGenerationTaskSnapshot({
  taskId,
  conversationId,
}: {
  taskId: string | number
  conversationId?: string | number | null
}) {
  if (conversationId != null && String(conversationId).trim() !== '') {
    return agentApi.getHarnessGenerationTask(String(conversationId), taskId)
  }

  return generationApi.queryTask(taskId as number)
}
