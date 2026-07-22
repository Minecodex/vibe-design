import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'

import { agentApi } from '@/api/endpoints/agent'
import {
  HOME_CHAT_PPT_REGENERATE_STATE_MESSAGE,
  isHomeChatPptRegenerateSlideMessage,
  type HomeChatPptRegenerateStateMessage,
} from './homeChatPptPreviewMessaging'

interface HomeChatDocHtmlPreviewProps {
  conversationId: string
  previewFilePath: string
  title: string
  onPresentationRegenerateSlide?: (slideIndex: number) => void
  isPresentationRegenerateDisabled?: boolean
}

export function HomeChatDocHtmlPreview({
  conversationId,
  previewFilePath,
  title,
  onPresentationRegenerateSlide,
  isPresentationRegenerateDisabled = false,
}: HomeChatDocHtmlPreviewProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)

  useEffect(() => {
    let cancelled = false
    setPreviewUrl(null)
    setError(null)

    agentApi.createWorkspacePreviewToken(conversationId)
      .then(({ preview_token }) => {
        if (cancelled) {
          return
        }
        setPreviewUrl(
          agentApi.getWorkspaceHtmlPreviewUrl(
            conversationId,
            previewFilePath,
            preview_token,
          ),
        )
      })
      .catch(() => {
        if (!cancelled) {
          setError('Failed to load document preview.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [conversationId, previewFilePath])

  useEffect(() => {
    if (!onPresentationRegenerateSlide) {
      return
    }

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) {
        return
      }
      if (!isHomeChatPptRegenerateSlideMessage(event.data)) {
        return
      }
      onPresentationRegenerateSlide(event.data.slideIndex)
    }

    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [onPresentationRegenerateSlide])

  useEffect(() => {
    if (!iframeRef.current?.contentWindow) {
      return
    }

    const message: HomeChatPptRegenerateStateMessage = {
      type: HOME_CHAT_PPT_REGENERATE_STATE_MESSAGE,
      disabled: isPresentationRegenerateDisabled,
    }
    iframeRef.current.contentWindow.postMessage(message, '*')
  }, [isPresentationRegenerateDisabled, previewUrl])

  if (error) {
    return <div className="px-4 text-sm text-red-500">{error}</div>
  }

  if (!previewUrl) {
    return (
      <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Loading document preview...</span>
      </div>
    )
  }

  return (
    <iframe
      ref={iframeRef}
      title={title}
      src={previewUrl}
      className="h-full w-full border-0 bg-white"
      sandbox="allow-same-origin allow-scripts allow-forms allow-modals allow-popups allow-downloads"
      data-testid="home-chat-doc-html-preview"
    />
  )
}
