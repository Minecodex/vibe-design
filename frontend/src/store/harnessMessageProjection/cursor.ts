import type { PresentationOpEvent, ProjectionSessionLike } from './types'

export function isPresentationOpEvent(event: PresentationOpEvent): boolean {
  return String(event?.type || '').startsWith('presentation.')
}

export function getPresentationSourceSequence(event: PresentationOpEvent): number | null {
  const candidates = [
    event.data?.source_sequence,
    event.data?.sourceSequence,
    event.payload?.source_sequence,
    event.payload?.sourceSequence,
    event.source_sequence,
    event.sequence,
  ]
  for (const candidate of candidates) {
    const source = Number(candidate)
    if (Number.isFinite(source) && source > 0) {
      return source
    }
  }
  return null
}

export function getPresentationOpId(event: PresentationOpEvent): string {
  const opId = String(event.data?.op_id ?? event.payload?.op_id ?? event.op_id ?? '').trim()
  if (opId && !hasUnassignedPayloadSequence(event)) {
    return opId
  }
  const sequence = getPresentationSourceSequence(event) ?? 0
  const blockKey = String(event.data?.block_key ?? event.payload?.block_key ?? '')
  return `${event.type}:${sequence}:${blockKey}`
}

function hasUnassignedPayloadSequence(event: PresentationOpEvent): boolean {
  const candidates = [
    event.data?.source_sequence,
    event.data?.sourceSequence,
    event.payload?.source_sequence,
    event.payload?.sourceSequence,
  ]
  return candidates.some((candidate) => {
    if (candidate == null) {
      return false
    }
    const parsed = Number(candidate)
    return !Number.isFinite(parsed) || parsed <= 0
  })
}

export function hasAppliedPresentationOp(session: ProjectionSessionLike, event: PresentationOpEvent): boolean {
  const opId = getPresentationOpId(event)
  return (session.appliedPresentationOps || []).includes(opId)
}

export function markPresentationOpApplied<T extends ProjectionSessionLike>(session: T, event: PresentationOpEvent): T {
  const opId = getPresentationOpId(event)
  const sequence = getPresentationSourceSequence(event)
  const applied = session.appliedPresentationOps || []
  return {
    ...session,
    lastSequence: sequence == null ? session.lastSequence : Math.max(session.lastSequence, sequence),
    appliedPresentationOps: applied.includes(opId)
      ? applied
      : [...applied.slice(-199), opId],
  }
}

