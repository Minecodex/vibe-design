import { clearSession, loadSession, saveSession } from './storage'
import { normalizeServerBaseUrl } from './config'

export async function refreshAccessToken(): Promise<string> {
  const session = await loadSession()
  if (!session) {
    throw new Error('Missing session')
  }

  const response = await fetch(
    `${normalizeServerBaseUrl(session.serverBaseUrl)}/api/v1/auth/refresh`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        refresh_token: session.refreshToken,
      }),
    },
  )

  if (!response.ok) {
    await clearSession()
    throw new Error('Refresh failed')
  }

  const data = await response.json() as {
    access_token: string
    refresh_token: string
  }

  await saveSession({
    ...session,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  })

  return data.access_token
}

export interface PromptExtractionResponse {
  prompt: string
  prompts?: Partial<Record<'zh-CN' | 'en-US', string>>
  language: 'zh-CN' | 'en-US'
  model: string
  amountCents?: number
  amount?: number
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [header, data] = dataUrl.split(',', 2)
  if (!header || !data) {
    throw new Error('Invalid image data')
  }

  const mimeMatch = header.match(/^data:(.+);base64$/)
  const mimeType = mimeMatch?.[1] || 'image/png'
  const binary = atob(data)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return new Blob([bytes], { type: mimeType })
}

function resolvePromptExtractionError(status: number): string {
  if (status === 401 || status === 403) {
    return '登录已失效，请重新登录'
  }
  if (status === 402) {
    return '余额不足'
  }
  if (status === 413) {
    return '图片过大'
  }
  return '提取失败'
}

export async function extractPromptFromImageDataUrl(
  imageDataUrl: string,
  locale: 'zh-CN' | 'en-US',
): Promise<PromptExtractionResponse> {
  const session = await loadSession()
  if (!session) {
    throw new Error('请先登录插件')
  }

  const makeRequest = async (accessToken: string) => {
    const formData = new FormData()
    formData.append(
      'image',
      dataUrlToBlob(imageDataUrl),
      'prompt-extractor.png',
    )
    formData.append('locale', locale)

    return fetch(
      `${normalizeServerBaseUrl(session.serverBaseUrl)}/api/v1/extension/prompt-extractor/analyze`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Accept-Language': locale,
        },
        body: formData,
      },
    )
  }

  let response = await makeRequest(session.accessToken)
  if (response.status === 401) {
    const nextAccessToken = await refreshAccessToken()
    response = await makeRequest(nextAccessToken)
  }

  if (!response.ok) {
    throw new Error(resolvePromptExtractionError(response.status))
  }

  const data = await response.json() as {
    prompt: string
    prompts?: Partial<Record<'zh-CN' | 'en-US', string>>
    language: 'zh-CN' | 'en-US'
    model: string
    amount_cents?: number
    amountCents?: number
    amount?: number
  }
  const amountCents = data.amount_cents ?? data.amountCents ?? data.amount

  return {
    prompt: data.prompt,
    prompts: data.prompts,
    language: data.language,
    model: data.model,
    amountCents,
  }
}
