import { createRoot, Root } from 'react-dom/client'

import { AnchorPoint, PromptResultView } from './PromptResultView'
import { PromptExtractionResponse } from './lib/api'
import { StoredPromptJob } from './lib/storage'

interface OverlayMessage {
  type: 'prompt-extractor.open-overlay'
  jobId: string
}

interface ExtractPromptMessage {
  type: 'prompt-extractor.extract-prompt'
  imageDataUrl: string
  locale: 'zh-CN' | 'en-US'
}

interface InPagePromptOverlayProps {
  initialJob?: StoredPromptJob
  jobId?: string
  anchorPoint?: AnchorPoint
  onClose: () => void
  requestPrompt?: (
    imageDataUrl: string,
    locale: 'zh-CN' | 'en-US',
  ) => Promise<PromptExtractionResponse>
}

declare const chrome:
  | {
      runtime?: {
        onMessage?: {
          addListener: (
            callback: (
              message: unknown,
              sender?: unknown,
            sendResponse?: (response?: unknown) => void,
            ) => void,
          ) => void
        }
        sendMessage?: (message: ExtractPromptMessage) => Promise<{
          ok: boolean
          data?: PromptExtractionResponse
          error?: string
        }>
      }
    }
  | undefined

let overlayHost: HTMLDivElement | null = null
let overlayRoot: Root | null = null
let lastAnchorPoint: AnchorPoint | null = null

function unmountOverlay() {
  overlayRoot?.unmount()
  overlayRoot = null
  overlayHost?.remove()
  overlayHost = null
}

function ensureOverlayRoot() {
  if (overlayHost && overlayRoot) {
    return overlayRoot
  }

  overlayHost = document.createElement('div')
  overlayHost.id = 'prompt-extractor-overlay-root'
  document.body.appendChild(overlayHost)
  overlayRoot = createRoot(overlayHost)
  return overlayRoot
}

function isOverlayMessage(message: unknown): message is OverlayMessage {
  if (!message || typeof message !== 'object') {
    return false
  }

  const candidate = message as Partial<OverlayMessage>
  return candidate.type === 'prompt-extractor.open-overlay' && typeof candidate.jobId === 'string'
}

function readAnchorPoint() {
  return lastAnchorPoint || {
    x: Math.round(window.innerWidth * 0.5) - 120,
    y: Math.round(window.innerHeight * 0.24),
  }
}

function mountOverlay(jobId: string) {
  const root = ensureOverlayRoot()
  root.render(<InPagePromptOverlay jobId={jobId} anchorPoint={readAnchorPoint()} onClose={unmountOverlay} />)
}

function rememberContextAnchor(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof Element)) {
    return
  }

  const image = target.closest('img')
  if (!image) {
    return
  }

  lastAnchorPoint = {
    x: event.clientX,
    y: event.clientY,
  }
}

async function requestPromptInBackground(
  imageDataUrl: string,
  locale: 'zh-CN' | 'en-US',
): Promise<PromptExtractionResponse> {
  if (!chrome?.runtime?.sendMessage) {
    throw new Error('提取服务不可用')
  }

  const response = await chrome.runtime.sendMessage({
    type: 'prompt-extractor.extract-prompt',
    imageDataUrl,
    locale,
  })

  if (!response.ok || !response.data) {
    throw new Error(response.error || '提取失败')
  }

  return response.data
}

export function InPagePromptOverlay({
  initialJob,
  jobId,
  anchorPoint,
  onClose,
  requestPrompt,
}: InPagePromptOverlayProps) {
  return (
    <PromptResultView
      initialJob={initialJob}
      jobId={jobId}
      anchorPoint={anchorPoint}
      mode="popover"
      onClose={onClose}
      requestPrompt={requestPrompt || requestPromptInBackground}
    />
  )
}

if (typeof document !== 'undefined') {
  document.addEventListener('contextmenu', rememberContextAnchor, true)
}

if (typeof document !== 'undefined' && typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message) => {
    if (!isOverlayMessage(message)) {
      return
    }

    mountOverlay(message.jobId)
  })
}
