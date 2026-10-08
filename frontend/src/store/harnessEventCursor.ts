type HarnessSnapshotWithProjection = {
    projection?: Record<string, unknown> | null
    event_stream?: Record<string, unknown> | null
    eventStream?: Record<string, unknown> | null
}

export function resolveHarnessSnapshotEventSequence(detail: HarnessSnapshotWithProjection): number {
    const projection = detail.projection && typeof detail.projection === 'object'
        ? detail.projection
        : {}
    const eventStream = (
        detail.event_stream && typeof detail.event_stream === 'object'
            ? detail.event_stream
            : detail.eventStream && typeof detail.eventStream === 'object'
                ? detail.eventStream
                : {}
    )
    return normalizeSequence(
        projection.event_last_sequence
        ?? projection.last_event_sequence
        ?? projection.latest_event_sequence
        ?? eventStream.last_sequence
        ?? eventStream.lastSequence
        ?? 0,
    )
}

function normalizeSequence(value: unknown): number {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}
