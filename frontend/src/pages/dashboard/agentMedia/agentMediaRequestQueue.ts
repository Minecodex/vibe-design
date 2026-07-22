const MAX_CONCURRENT_MEDIA_REQUESTS = 4

let activeRequestCount = 0
const pendingRequests: Array<() => void> = []

export async function enqueueAgentMediaRequest<T>(task: () => Promise<T>): Promise<T> {
  if (activeRequestCount >= MAX_CONCURRENT_MEDIA_REQUESTS) {
    await new Promise<void>((resolve) => pendingRequests.push(resolve))
  }
  activeRequestCount += 1
  try {
    return await task()
  } finally {
    activeRequestCount = Math.max(0, activeRequestCount - 1)
    const next = pendingRequests.shift()
    next?.()
  }
}

export function __resetAgentMediaRequestQueueForTests(): void {
  activeRequestCount = 0
  pendingRequests.splice(0, pendingRequests.length)
}
