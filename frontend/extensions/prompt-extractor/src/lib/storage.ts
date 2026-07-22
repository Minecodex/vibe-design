export interface StoredSession {
  serverBaseUrl: string
  accessToken: string
  refreshToken: string
}

export interface StoredPromptJob {
  id: string
  imageDataUrl: string
  locale: 'zh-CN' | 'en-US'
  prompt?: string
  prompts?: Partial<Record<'zh-CN' | 'en-US', string>>
  amountCents?: number
  model?: string
}

declare const chrome: {
  storage: {
    local: {
      get: (key?: string | string[]) => Promise<Record<string, unknown>>
      set: (values: Record<string, unknown>) => Promise<void>
      remove: (key: string | string[]) => Promise<void>
    }
  }
}

const SESSION_STORAGE_KEY = 'promptExtractor.session'
const PROMPT_JOB_STORAGE_PREFIX = 'promptExtractor.job.'
const memoryStorage = new Map<string, unknown>()

function getStorageArea() {
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    return chrome.storage.local
  }

  return {
    async get(key?: string | string[]) {
      if (!key) {
        return Object.fromEntries(memoryStorage.entries())
      }
      if (Array.isArray(key)) {
        return Object.fromEntries(key.map((item) => [item, memoryStorage.get(item)]))
      }
      return { [key]: memoryStorage.get(key) }
    },
    async set(values: Record<string, unknown>) {
      Object.entries(values).forEach(([key, value]) => memoryStorage.set(key, value))
    },
    async remove(key: string | string[]) {
      const keys = Array.isArray(key) ? key : [key]
      keys.forEach((item) => memoryStorage.delete(item))
    },
  }
}

export async function loadSession(): Promise<StoredSession | null> {
  const storageArea = getStorageArea()
  const result = await storageArea.get(SESSION_STORAGE_KEY)
  const session = result[SESSION_STORAGE_KEY]
  if (!session || typeof session !== 'object') {
    return null
  }

  const candidate = session as Partial<StoredSession>
  if (!candidate.serverBaseUrl || !candidate.accessToken || !candidate.refreshToken) {
    return null
  }

  return {
    serverBaseUrl: candidate.serverBaseUrl,
    accessToken: candidate.accessToken,
    refreshToken: candidate.refreshToken,
  }
}

export async function saveSession(session: StoredSession): Promise<void> {
  const storageArea = getStorageArea()
  await storageArea.set({
    [SESSION_STORAGE_KEY]: session,
  })
}

export async function clearSession(): Promise<void> {
  const storageArea = getStorageArea()
  await storageArea.remove(SESSION_STORAGE_KEY)
}

export async function savePromptJob(job: StoredPromptJob): Promise<void> {
  const storageArea = getStorageArea()
  await storageArea.set({
    [`${PROMPT_JOB_STORAGE_PREFIX}${job.id}`]: job,
  })
}

export async function loadPromptJob(jobId: string): Promise<StoredPromptJob | null> {
  const storageArea = getStorageArea()
  const result = await storageArea.get(`${PROMPT_JOB_STORAGE_PREFIX}${jobId}`)
  const job = result[`${PROMPT_JOB_STORAGE_PREFIX}${jobId}`]
  if (!job || typeof job !== 'object') {
    return null
  }

  const candidate = job as Partial<StoredPromptJob>
  if (!candidate.id || !candidate.imageDataUrl || !candidate.locale) {
    return null
  }

  return {
    id: candidate.id,
    imageDataUrl: candidate.imageDataUrl,
    locale: candidate.locale,
    prompt: candidate.prompt,
    prompts: candidate.prompts,
    amountCents: candidate.amountCents,
    model: candidate.model,
  }
}

export async function removePromptJob(jobId: string): Promise<void> {
  const storageArea = getStorageArea()
  await storageArea.remove(`${PROMPT_JOB_STORAGE_PREFIX}${jobId}`)
}
