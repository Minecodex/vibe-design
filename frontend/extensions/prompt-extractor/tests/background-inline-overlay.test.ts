import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchImageAsDataUrl = vi.fn()
const loadSession = vi.fn()
const savePromptJob = vi.fn()
const extractPromptFromImageDataUrl = vi.fn()

vi.mock('../src/lib/imageCapture', () => ({
  fetchImageAsDataUrl,
}))

vi.mock('../src/lib/storage', () => ({
  loadSession,
  savePromptJob,
}))

vi.mock('../src/lib/api', () => ({
  extractPromptFromImageDataUrl,
}))

describe('prompt extractor background messaging', () => {
  let onInstalledHandler: (() => void) | undefined
  let onClickedHandler: ((info: Record<string, unknown>, tab?: { id?: number }) => Promise<void>) | undefined
  let onMessageHandler:
    | ((message: unknown, sender: unknown, sendResponse: (response?: unknown) => void) => boolean | void)
    | undefined

  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
    onInstalledHandler = undefined
    onClickedHandler = undefined
    onMessageHandler = undefined

    ;(globalThis as { chrome?: unknown }).chrome = {
      contextMenus: {
        create: vi.fn(),
        onClicked: {
          addListener: vi.fn((callback: typeof onClickedHandler) => {
            onClickedHandler = callback
          }),
        },
      },
      runtime: {
        onInstalled: {
          addListener: vi.fn((callback: typeof onInstalledHandler) => {
            onInstalledHandler = callback
          }),
        },
        onMessage: {
          addListener: vi.fn((callback: typeof onMessageHandler) => {
            onMessageHandler = callback
          }),
        },
        openOptionsPage: vi.fn(),
        getURL: vi.fn((path: string) => `chrome-extension://test/${path}`),
      },
      tabs: {
        sendMessage: vi.fn(),
      },
      windows: {
        create: vi.fn(),
      },
    }
  })

  it('sends the extraction job to the current tab instead of opening a popup window', async () => {
    loadSession.mockResolvedValue({
      serverBaseUrl: 'https://example.com',
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    })
    fetchImageAsDataUrl.mockResolvedValue('data:image/png;base64,ZmFrZQ==')

    await import('../src/background')

    expect(onClickedHandler).toBeTypeOf('function')

    await onClickedHandler?.(
      {
        menuItemId: 'prompt-extractor.extract',
        srcUrl: 'https://example.com/image.png',
      },
      { id: 42 },
    )

    expect(savePromptJob).toHaveBeenCalledTimes(1)
    expect((globalThis as { chrome: { tabs: { sendMessage: ReturnType<typeof vi.fn> } } }).chrome.tabs.sendMessage).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        type: 'prompt-extractor.open-overlay',
      }),
    )
    expect((globalThis as { chrome: { windows: { create: ReturnType<typeof vi.fn> } } }).chrome.windows.create).not.toHaveBeenCalled()
  })

  it('handles prompt extraction in the background worker so the page avoids direct CORS requests', async () => {
    extractPromptFromImageDataUrl.mockResolvedValue({
      prompt: 'a pink soda bottle on a cyan background',
      prompts: {
        'zh-CN': '一瓶粉色苏打饮料，纯青色背景',
        'en-US': 'a pink soda bottle on a cyan background',
      },
      language: 'en-US',
      amountCents: 11,
      model: 'gemini-3.1-pro-preview',
    })

    await import('../src/background')

    expect(onMessageHandler).toBeTypeOf('function')

    const response = await new Promise<unknown>((resolve) => {
      const shouldKeepChannelOpen = onMessageHandler?.(
        {
          type: 'prompt-extractor.extract-prompt',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'en-US',
        },
        {},
        resolve,
      )

      expect(shouldKeepChannelOpen).toBe(true)
    })

    expect(extractPromptFromImageDataUrl).toHaveBeenCalledWith(
      'data:image/png;base64,ZmFrZQ==',
      'en-US',
    )
    expect(response).toEqual({
      ok: true,
      data: {
        prompt: 'a pink soda bottle on a cyan background',
        prompts: {
          'zh-CN': '一瓶粉色苏打饮料，纯青色背景',
          'en-US': 'a pink soda bottle on a cyan background',
        },
        language: 'en-US',
        amountCents: 11,
        model: 'gemini-3.1-pro-preview',
      },
    })
  })
})
