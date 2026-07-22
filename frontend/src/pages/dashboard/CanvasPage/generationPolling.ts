export type SerialPollingTask = () => Promise<number | null>

export const GENERATION_TASK_STATUS_POLL_INTERVAL_MS = 3000
export const GENERATION_TASK_POLL_ERROR_RETRY_INTERVAL_MS = 3000

export function startSerialPolling(task: SerialPollingTask): () => void {
  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const run = async () => {
    const nextDelay = await task()
    if (cancelled || nextDelay == null) return
    timer = setTimeout(run, nextDelay)
  }

  void run()

  return () => {
    cancelled = true
    if (timer) {
      clearTimeout(timer)
    }
  }
}
