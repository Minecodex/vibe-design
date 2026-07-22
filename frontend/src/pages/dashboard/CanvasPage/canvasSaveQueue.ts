/**
 * Runs async tasks one at a time, coalescing to the most recently scheduled value.
 *
 * Canvas autosave sends the FULL canvas snapshot on every generation event. Without
 * serialization those PUTs overlap and can arrive out of order, so an older snapshot can
 * land after a newer one and silently drop an item another event just added (defects D3/D4).
 *
 * This runner guarantees:
 *  - at most one task in flight at a time (no out-of-order network arrival), and
 *  - only the latest pending value is flushed after the in-flight task finishes (older
 *    superseded snapshots are dropped, since each snapshot is a complete canvas state),
 * so the newest canvas state always wins and rapid bursts collapse into few requests.
 *
 * The returned `schedule` resolves once the in-flight drain it kicked off has finished; a
 * call made while a drain is already running resolves immediately after enqueueing (the
 * already-running drain will flush it). A task that throws is swallowed via `onError` so one
 * failed save never wedges the queue.
 */
export function createCoalescingRunner<T>(
  run: (value: T) => Promise<void>,
  onError?: (error: unknown, value: T) => void,
): (value: T) => Promise<void> {
  let inFlight = false
  let pending: { value: T } | null = null

  return async function schedule(value: T): Promise<void> {
    pending = { value }
    if (inFlight) return
    inFlight = true
    try {
      while (pending) {
        const next = pending
        pending = null
        try {
          await run(next.value)
        } catch (error) {
          onError?.(error, next.value)
        }
      }
    } finally {
      inFlight = false
    }
  }
}
