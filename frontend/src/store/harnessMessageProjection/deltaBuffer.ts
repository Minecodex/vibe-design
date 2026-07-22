import { applyPresentationOpToSession } from './reducer'
import type { PresentationOpEvent, ProjectionSessionLike } from './types'

export interface PresentationDeltaBuffer<TSession extends ProjectionSessionLike = ProjectionSessionLike> {
  push(event: PresentationOpEvent): boolean
  flush(session: TSession): TSession
  clear(): void
  size(): number
}

export function createPresentationDeltaBuffer<TSession extends ProjectionSessionLike = ProjectionSessionLike>(): PresentationDeltaBuffer<TSession> {
  const events: PresentationOpEvent[] = []

  return {
    push(event) {
      if (event.type !== 'presentation.block.delta') {
        return false
      }
      events.push(event)
      return true
    },
    flush(session) {
      if (events.length === 0) {
        return session
      }
      const pending = events.splice(0, events.length)
      return pending.reduce(
        (nextSession, event) => applyPresentationOpToSession(nextSession, event),
        session,
      )
    },
    clear() {
      events.splice(0, events.length)
    },
    size() {
      return events.length
    },
  }
}

export function createNoopPresentationDeltaBuffer<TSession extends ProjectionSessionLike = ProjectionSessionLike>(): PresentationDeltaBuffer<TSession> {
  return {
    push() {
      return false
    },
    flush(session) {
      return session
    },
    clear() {},
    size() {
      return 0
    },
  }
}
