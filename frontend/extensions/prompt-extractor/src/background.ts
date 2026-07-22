import { extractPromptFromImageDataUrl } from './lib/api'
import { fetchImageAsDataUrl } from './lib/imageCapture'
import { loadSession, savePromptJob } from './lib/storage'

interface ExtractPromptMessage {
  type: 'prompt-extractor.extract-prompt'
  imageDataUrl: string
  locale: 'zh-CN' | 'en-US'
}

declare const chrome: {
  contextMenus: {
    create: (createProperties: Record<string, unknown>) => void
    onClicked: {
      addListener: (
        callback: (
          info: Record<string, unknown>,
          tab?: { id?: number },
        ) => void,
      ) => void
    }
  }
  runtime: {
    onInstalled: {
      addListener: (callback: () => void) => void
    }
    onMessage: {
      addListener: (
        callback: (
          message: unknown,
          sender: unknown,
          sendResponse: (response?: unknown) => void,
        ) => boolean | void,
      ) => void
    }
    openOptionsPage: () => void
  }
  tabs: {
    sendMessage: (tabId: number, message: Record<string, unknown>) => Promise<unknown>
  }
}

function isExtractPromptMessage(message: unknown): message is ExtractPromptMessage {
  if (!message || typeof message !== 'object') {
    return false
  }

  const candidate = message as Partial<ExtractPromptMessage>
  return (
    candidate.type === 'prompt-extractor.extract-prompt' &&
    typeof candidate.imageDataUrl === 'string' &&
    (candidate.locale === 'zh-CN' || candidate.locale === 'en-US')
  )
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'prompt-extractor.extract',
    title: '提取提示词',
    contexts: ['image'],
  })
})

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!isExtractPromptMessage(message)) {
    return
  }

  void (async () => {
    try {
      const result = await extractPromptFromImageDataUrl(message.imageDataUrl, message.locale)
      sendResponse({
        ok: true,
        data: result,
      })
    } catch (error) {
      sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : '提取失败',
      })
    }
  })()

  return true
})

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== 'prompt-extractor.extract') {
    return
  }

  const session = await loadSession()
  if (!session) {
    chrome.runtime.openOptionsPage()
    return
  }

  const srcUrl = typeof info.srcUrl === 'string' ? info.srcUrl : ''
  if (!srcUrl || typeof tab?.id !== 'number') {
    return
  }

  try {
    const imageDataUrl = await fetchImageAsDataUrl(srcUrl)
    const locale = navigator.language.startsWith('zh') ? 'zh-CN' : 'en-US'
    const jobId = `job-${Date.now()}`

    await savePromptJob({
      id: jobId,
      imageDataUrl,
      locale,
    })

    await chrome.tabs.sendMessage(tab.id, {
      type: 'prompt-extractor.open-overlay',
      jobId,
    })
  } catch {
    chrome.runtime.openOptionsPage()
  }
})
