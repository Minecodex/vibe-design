import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach } from 'vitest'
import { describe, expect, it, vi } from 'vitest'

import { InPagePromptOverlay } from '../src/content'

describe('prompt extractor in-page popover', () => {
  beforeEach(() => {
    ;(globalThis as { chrome?: unknown }).chrome = undefined
  })

  it('renders as an anchored floating card without a fullscreen backdrop and closes on outside click', async () => {
    const requestPrompt = vi.fn().mockResolvedValueOnce({
      prompt: '一瓶粉色饮料，红色瓶盖，白色标签，纯青色背景，3D数字艺术风格。',
      prompts: {
        'zh-CN': '一瓶粉色饮料，红色瓶盖，白色标签，纯青色背景，3D数字艺术风格。',
        'en-US': 'a pink drink bottle with a red cap, white label, cyan background, 3D digital art style.',
      },
      language: 'zh-CN',
      amountCents: 11,
      model: 'gemini-3.1-pro-preview',
    })
    const handleClose = vi.fn()

    render(
      <InPagePromptOverlay
        initialJob={{
          id: 'job-1',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'zh-CN',
        }}
        anchorPoint={{ x: 320, y: 220 }}
        onClose={handleClose}
        requestPrompt={requestPrompt}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /提取提示词|Prompt Extractor/ })).toBeTruthy()
    })

    expect(screen.queryByTestId('overlay-backdrop')).toBeNull()
    expect(screen.getByTestId('result-popover-shell')).toBeTruthy()
    expect(screen.getByText('Gemini 3.1 Pro')).toBeTruthy()
    expect(screen.queryByText(/计费信息|Usage/)).toBeNull()
    expect(screen.queryByText(/本次消耗 ¥0.11|This run used ¥0.11/)).toBeNull()

    await userEvent.click(document.body)

    expect(handleClose).toHaveBeenCalledTimes(1)
  })

  it('delegates prompt extraction to the extension background runtime by default', async () => {
    const sendMessage = vi.fn().mockResolvedValue({
      ok: true,
      data: {
        prompt: 'a pink bottle on a cyan backdrop',
        prompts: {
          'zh-CN': '一瓶粉色饮料，纯青色背景',
          'en-US': 'a pink bottle on a cyan backdrop',
        },
        language: 'en-US',
        amountCents: 11,
        model: 'gemini-3.1-pro-preview',
      },
    })

    ;(globalThis as { chrome?: unknown }).chrome = {
      runtime: {
        sendMessage,
      },
    }

    render(
      <InPagePromptOverlay
        initialJob={{
          id: 'job-2',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'en-US',
        }}
        anchorPoint={{ x: 240, y: 180 }}
        onClose={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith({
        type: 'prompt-extractor.extract-prompt',
        imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
        locale: 'en-US',
      })
    })

    expect(screen.getByLabelText('prompt-output').textContent).toContain('pink bottle')
  })
})

