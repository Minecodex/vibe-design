import { wireRecord } from './harnessWireFields'
import {
  applyGenerationProjectionUpdate,
  createGenerationProjectionState,
  type GenerationProjectionState,
} from './generationProjection'
import {
  buildCanvasItemFromGenerationEvent,
  buildCanvasPlaceholderFromGenerationEvent,
  buildCanvasRevisionMetaFromGenerationEvent,
  buildGenerationProjectionUpdateFromEvent,
  isGenerationProjectionEvent,
} from './generationEventProjection'

type GenerationEventLike = {
  type: string
  sequence?: number | null
  data?: Record<string, unknown> | null
}

export type CanvasGenerationProjectionSession = {
  generationProjection?: GenerationProjectionState
}

export type CanvasGenerationProjectionResult<T extends CanvasGenerationProjectionSession> = {
  session: T & { generationProjection: GenerationProjectionState }
  canvasUpdate?: { action: string; item: Record<string, unknown>; meta?: Record<string, unknown> }
  handled: boolean
}

export function applyCanvasGenerationEvent<T extends CanvasGenerationProjectionSession>(
  session: T,
  event: GenerationEventLike,
  conversationId?: number | string | null,
): CanvasGenerationProjectionResult<T> {
  if (!isGenerationProjectionEvent(event)) {
    return {
      session: {
        ...session,
        generationProjection: session.generationProjection ?? createGenerationProjectionState(),
      },
      handled: false,
    }
  }

  const update = buildGenerationProjectionUpdateFromEvent(event)
  if (!update) {
    return {
      session: {
        ...session,
        generationProjection: session.generationProjection ?? createGenerationProjectionState(),
      },
      handled: true,
    }
  }

  const projection = applyGenerationProjectionUpdate(
    session.generationProjection ?? createGenerationProjectionState(),
    update,
  )
  const nextSession = {
    ...session,
    generationProjection: projection.state,
  }
  const canvasRevisionMeta = buildCanvasRevisionMetaFromGenerationEvent(event)

  return {
    session: nextSession,
    handled: true,
    canvasUpdate: hasDeletedCanvasItem(event)
      ? undefined
      : projection.canvasInsertion
      ? {
        action: 'add_generated_media',
        item: buildCanvasItemFromGenerationEvent(event, projection.canvasInsertion, conversationId),
        ...(canvasRevisionMeta ? { meta: canvasRevisionMeta } : {}),
      }
      : projection.canvasPlaceholder
        ? {
          action: 'add',
          item: buildCanvasPlaceholderFromGenerationEvent(event, projection.canvasPlaceholder, conversationId),
          ...(canvasRevisionMeta ? { meta: canvasRevisionMeta } : {}),
        }
      : undefined,
  }
}

function hasDeletedCanvasItem(event: GenerationEventLike): boolean {
  const data = event.data || {}
  const payload = wireRecord(data.payload) || {}
  const result = wireRecord(data.result) || {}
  return data.canvas_item_deleted === true || payload.canvas_item_deleted === true || result.canvas_item_deleted === true
}
