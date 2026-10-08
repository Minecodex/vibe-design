import { isTurnCompletedEvent } from './harnessTurnProtocol'

export type HarnessStreamSource<TEvent> = (
  conversationId: string,
  afterSequenceOrSignal?: number | AbortSignal,
  signalMaybe?: AbortSignal,
) => AsyncIterable<TEvent>

export type HarnessStreamSessionOptions<TEvent> = {
  conversationId: string
  lastSequence?: number
  getLastSequence?: () => number
  getEventSequence?: (event: TEvent) => number | null | undefined
  skipDuplicateSequences?: boolean
  reconnectDelayMs?: number
  shouldReconnect?: (error: unknown | null, controller: AbortController) => boolean | Promise<boolean>
  isTerminalEvent?: (event: TEvent) => boolean
  onTransportClosedWithoutTerminal?: () => boolean | Promise<boolean>
  stream: HarnessStreamSource<TEvent>
  onEvent: (event: TEvent) => void
  onError?: (error: unknown) => void
  onClose?: (controller: AbortController) => void | Promise<void>
}

export type HarnessStreamSession = {
  controller: AbortController
  abort: () => void
}

export function startHarnessStreamSession<TEvent>({
  conversationId,
  lastSequence = 0,
  getLastSequence,
  getEventSequence = defaultGetEventSequence,
  skipDuplicateSequences = true,
  reconnectDelayMs = 0,
  shouldReconnect,
  isTerminalEvent = defaultIsTerminalEvent,
  onTransportClosedWithoutTerminal,
  stream,
  onEvent,
  onError,
  onClose,
}: HarnessStreamSessionOptions<TEvent>): HarnessStreamSession {
  const controller = new AbortController()
  let latestSequence = lastSequence > 0 ? lastSequence : 0
  let sawTerminalEvent = false

  void (async () => {
    try {
      while (!controller.signal.aborted) {
        let streamError: unknown | null = null
        try {
          const afterSequence = resolveAfterSequence(latestSequence, getLastSequence)
          const source = afterSequence == null
            ? stream(conversationId, controller.signal)
            : stream(conversationId, afterSequence, controller.signal)
          for await (const event of source) {
            const eventSequence = normalizeEventSequence(getEventSequence(event))
            if (skipDuplicateSequences && eventSequence != null && eventSequence <= latestSequence) {
              continue
            }
            onEvent(event)
            if (isTerminalEvent(event)) {
              sawTerminalEvent = true
            }
            if (eventSequence != null) {
              latestSequence = Math.max(latestSequence, eventSequence)
            }
          }
        } catch (error: any) {
          if (error?.name === 'AbortError') {
            break
          }
          streamError = error
          onError?.(error)
        }

        if (controller.signal.aborted) {
          break
        }

        if (sawTerminalEvent) {
          break
        }

        const reconnect = onTransportClosedWithoutTerminal
          ? await onTransportClosedWithoutTerminal()
          : await shouldReconnect?.(streamError, controller)
        if (!reconnect) {
          break
        }

        await waitForReconnectDelay(reconnectDelayMs, controller.signal)
      }
    } finally {
      await onClose?.(controller)
    }
  })()

  return {
    controller,
    abort: () => controller.abort(),
  }
}

function defaultIsTerminalEvent<TEvent>(event: TEvent): boolean {
  return isTurnCompletedEvent(event as any)
    || (event as { type?: unknown } | null)?.type === 'protocol_error'
}

function defaultGetEventSequence<TEvent>(event: TEvent): number | null {
  const sequence = (event as { sequence?: unknown } | null)?.sequence
  return normalizeEventSequence(sequence)
}

function normalizeEventSequence(sequence: unknown): number | null {
  return typeof sequence === 'number' && Number.isFinite(sequence) && sequence > 0
    ? sequence
    : null
}

function resolveAfterSequence(
  latestSequence: number,
  getLastSequence?: () => number,
): number | undefined {
  const externalSequence = normalizeEventSequence(getLastSequence?.())
  const afterSequence = Math.max(latestSequence, externalSequence ?? 0)
  return afterSequence > 0 ? afterSequence : undefined
}

function waitForReconnectDelay(delayMs: number, signal: AbortSignal): Promise<void> {
  if (delayMs <= 0) {
    return Promise.resolve()
  }

  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }

    const abort = () => {
      clearTimeout(timer)
      resolve()
    }

    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, delayMs)

    signal.addEventListener('abort', abort, { once: true })
  })
}
