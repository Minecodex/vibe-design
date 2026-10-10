import { errorName } from '@/utils/apiErrors'
import { agentApi, type AgentEvent } from '@/api/endpoints/agent'

const SETTLE_POLL_INTERVAL_MS = 250
const SETTLE_MAX_ATTEMPTS = 40 // ~10s ceiling before we give up and let the send proceed

/**
 * A run is "settled" for the purpose of starting a new turn once neither the
 * runtime status nor the run state reports an in-flight or still-cancelling run.
 *
 * Note: while a running turn is being cancelled the backend reports
 * `runtime_status: 'cancelled'` immediately but keeps `run_state: 'cancelling'`
 * until the worker actually tears the run down. The active-run guard keys off the
 * underlying run record, so we must wait for `run_state` to leave `cancelling`
 * (not just trust the terminal-looking `runtime_status`).
 */
function isHarnessRunSettledForSend(detail: { runtime_status?: unknown; run_state?: unknown }): boolean {
    const runtimeStatus = String(detail.runtime_status || '').trim().toLowerCase()
    const runState = String(detail.run_state || '').trim().toLowerCase()
    const isPending = (value: string) => value === 'running' || value === 'cancelling'
    return !isPending(runtimeStatus) && !isPending(runState)
}

/**
 * Detects the backend "active run" conflict (HTTP 409) raised when a new message
 * is submitted while a previous run is still running or tearing down. This is the
 * race that occurs when the user stops a run and immediately re-submits.
 */
export function isHarnessActiveRunConflict(err: unknown): boolean {
    if (!err) {
        return false
    }
    if ((err as { status?: number }).status === 409) {
        return true
    }
    const message = String((err as { message?: unknown }).message || '').toLowerCase()
    return message.includes('already has an active run')
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
    return new Promise((resolve) => {
        if (signal?.aborted) {
            resolve()
            return
        }
        const timer = setTimeout(() => {
            signal?.removeEventListener('abort', onAbort)
            resolve()
        }, ms)
        const onAbort = () => {
            clearTimeout(timer)
            resolve()
        }
        signal?.addEventListener('abort', onAbort, { once: true })
    })
}

/**
 * Polls the harness conversation until any in-flight (or still-cancelling) run
 * has fully settled, so a freshly submitted message is not rejected by the
 * backend active-run guard with a 409.
 *
 * Returns `true` once the run is settled, or `false` if the wait was aborted or
 * timed out (the caller should still attempt the send in that case).
 */
export async function waitForHarnessRunToSettle(
    conversationId: string,
    signal?: AbortSignal,
): Promise<boolean> {
    for (let attempt = 0; attempt < SETTLE_MAX_ATTEMPTS; attempt++) {
        if (signal?.aborted) {
            return false
        }
        let detail: { runtime_status?: unknown; run_state?: unknown } | null = null
        try {
            const res = await agentApi.getHarnessConversation(conversationId, signal)
            detail = res?.data ?? null
        } catch (err) {
            if (errorName(err) === 'AbortError') {
                return false
            }
            detail = null
        }
        if (detail && isHarnessRunSettledForSend(detail)) {
            return true
        }
        await delay(SETTLE_POLL_INTERVAL_MS, signal)
    }
    return false
}

/**
 * Wraps a harness turn stream so that an "active run" 409 (raised when the user
 * stops a run and immediately starts another streaming action before the backend
 * has finished tearing the previous run down) is recovered automatically: it
 * waits for the previous run to settle and retries the stream once, instead of
 * silently dropping the action and leaving the UI stuck on "thinking".
 *
 * `makeStream` is re-invoked on retry so it can read a fresh `after_sequence`.
 * `canRetry`, when provided, must return true for the retry to proceed (used to
 * skip retrying a send that has since been superseded by a newer one).
 */
export async function* withHarnessActiveRunRetry(
    conversationId: string,
    signal: AbortSignal | undefined,
    makeStream: () => AsyncGenerator<AgentEvent>,
    canRetry?: () => boolean,
): AsyncGenerator<AgentEvent> {
    for (let attempt = 0; ; attempt++) {
        try {
            for await (const event of makeStream()) {
                yield event
            }
            return
        } catch (err) {
            if (errorName(err) === 'AbortError') {
                throw err
            }
            if (
                attempt === 0
                && isHarnessActiveRunConflict(err)
                && (!canRetry || canRetry())
            ) {
                const settled = await waitForHarnessRunToSettle(conversationId, signal)
                if (!signal?.aborted && settled && (!canRetry || canRetry())) {
                    continue
                }
            }
            throw err
        }
    }
}
