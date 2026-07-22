const RUNTIME_ADAPTER_EVENT_TYPES = new Set([
  'asset_added',
  'asset_registered',
  'asset_removed',
  'canvas_update',
  'critique.below_threshold',
  'critique.degraded',
  'critique.failed',
  'critique.protocol_rejected',
  'critique.round_completed',
  'critique.shipped',
  'critique.started',
  'file_created',
  'file_current_version_changed',
  'file_published',
  'file_updated',
  'file_version_created',
  'generation_completed',
  'generation_failed',
  'generation_started',
  'item_completed',
  'item_started',
  'item_updated',
  'protocol_error',
  'run_preparing',
  'run_started',
  'turn_completed',
  'turn_started',
  'workspace_file_upserted',
])

export interface PresentationProtocolEventLike {
  type?: string | null
  data?: Record<string, unknown> | null
  payload?: Record<string, unknown> | null
}

export function shouldApplyRuntimeAdapterEvent(
  event: PresentationProtocolEventLike | null | undefined,
): boolean {
  const eventType = String(event?.type || '').trim()
  return RUNTIME_ADAPTER_EVENT_TYPES.has(eventType)
}
