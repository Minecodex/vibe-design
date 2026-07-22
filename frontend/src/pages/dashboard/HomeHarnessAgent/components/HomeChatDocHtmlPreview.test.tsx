import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomeChatDocHtmlPreview } from './HomeChatDocHtmlPreview'

const createWorkspacePreviewTokenMock = vi.fn()
const getWorkspaceHtmlPreviewUrlMock = vi.fn()

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    createWorkspacePreviewToken: (...args: unknown[]) => createWorkspacePreviewTokenMock(...args),
    getWorkspaceHtmlPreviewUrl: (...args: unknown[]) => getWorkspaceHtmlPreviewUrlMock(...args),
  },
}))

describe('HomeChatDocHtmlPreview', () => {
  beforeEach(() => {
    createWorkspacePreviewTokenMock.mockReset()
    getWorkspaceHtmlPreviewUrlMock.mockReset()
    createWorkspacePreviewTokenMock.mockResolvedValue({
      preview_token: 'preview-token',
    })
    getWorkspaceHtmlPreviewUrlMock.mockReturnValue('/preview/index.html')
  })

  it('forwards ppt regenerate messages from its iframe to the parent callback', async () => {
    const onPresentationRegenerateSlide = vi.fn()

    render(
      <HomeChatDocHtmlPreview
        conversationId="conv-1"
        previewFilePath="code/ppt-parser-html/index.html"
        title="deck.pptx"
        onPresentationRegenerateSlide={onPresentationRegenerateSlide}
      />,
    )

    const iframe = await screen.findByTestId('home-chat-doc-html-preview')
    const iframeWindow = {
      postMessage: vi.fn(),
    }
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      value: iframeWindow,
    })

    window.dispatchEvent(new MessageEvent('message', {
      source: iframeWindow as unknown as MessageEventSource,
      data: {
        type: 'home_harness_ppt_regenerate_slide',
        slideIndex: 3,
      },
    }))

    expect(onPresentationRegenerateSlide).toHaveBeenCalledWith(3)
  })

  it('syncs disabled state updates to the preview iframe when ppt actions are disabled', async () => {
    const { rerender } = render(
      <HomeChatDocHtmlPreview
        conversationId="conv-1"
        previewFilePath="code/ppt-parser-html/index.html"
        title="deck.pptx"
        isPresentationRegenerateDisabled={false}
      />,
    )

    const iframe = await screen.findByTestId('home-chat-doc-html-preview')
    const iframeWindow = {
      postMessage: vi.fn(),
    }
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      value: iframeWindow,
    })

    rerender(
      <HomeChatDocHtmlPreview
        conversationId="conv-1"
        previewFilePath="code/ppt-parser-html/index.html"
        title="deck.pptx"
        isPresentationRegenerateDisabled
      />,
    )

    await waitFor(() => {
      expect(iframeWindow.postMessage).toHaveBeenCalledWith(
        { type: 'home_harness_ppt_regenerate_state', disabled: true },
        '*',
      )
    })
  })
})
