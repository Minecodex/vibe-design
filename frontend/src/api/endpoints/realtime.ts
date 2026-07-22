import { apiClient } from '../client'
import { getApiBaseUrl } from '@/config/runtimeConfig'
import { storage } from '@/utils/storage'

export interface RealtimeNotification {
  v: 2
  kind: 'notify' | 'wakeup' | 'invalidate'
  name: string
  scope?: {
    user_id?: number | null
    project_id?: number | null
    conversation_id?: string | null
  } | null
  resource?: {
    type?: string | null
    id?: string | null
    version?: string | null
  } | null
  reason?: string | null
  emitted_at?: string | null
}

export interface RealtimeEvent {
  type: 'realtime_ready' | 'realtime_notification'
  data?: RealtimeNotification
}

function buildRealtimeUrl(projectId?: number | null): string {
  const params = new URLSearchParams()
  if (typeof projectId === 'number' && Number.isFinite(projectId)) {
    params.set('project_id', String(projectId))
  }
  const query = params.toString()
  return `${getApiBaseUrl()}/realtime/events${query ? `?${query}` : ''}`
}

async function fetchWithRefresh(url: string, signal?: AbortSignal): Promise<Response> {
  const token = storage.getToken() || ''
  let response = await fetch(url, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal,
  })
  if (response.status !== 401) {
    return response
  }
  const refreshToken = storage.getRefreshToken()
  if (!refreshToken) {
    return response
  }
  try {
    const refreshRes = await apiClient.post('/auth/refresh', { refresh_token: refreshToken })
    const newToken = refreshRes.data.access_token
    storage.setToken(newToken)
    storage.setRefreshToken(refreshRes.data.refresh_token)
    response = await fetch(url, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${newToken}`,
      },
      signal,
    })
  } catch {
    return response
  }
  return response
}

export async function* streamRealtimeEvents(
  options: { projectId?: number | null; signal?: AbortSignal } = {},
): AsyncGenerator<RealtimeEvent> {
  const response = await fetchWithRefresh(buildRealtimeUrl(options.projectId), options.signal)
  if (!response.ok || !response.body) {
    throw new Error(`Realtime stream failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        completed = true
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const trimmed = frame.trim()
        if (!trimmed.startsWith('data: ')) {
          continue
        }
        try {
          yield JSON.parse(trimmed.slice(6)) as RealtimeEvent
        } catch {
          // Ignore malformed realtime hints.
        }
      }
    }
  } finally {
    try {
      if (!completed && !options.signal?.aborted) {
        await reader.cancel()
      }
    } catch {
      // Ignore cancellation races.
    }
    reader.releaseLock?.()
  }
}
