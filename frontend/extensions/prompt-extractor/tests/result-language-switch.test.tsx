import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PromptResultApp } from '../src/result'

beforeEach(() => {
  Object.defineProperty(window, 'resizeTo', {
    value: vi.fn(),
    writable: true,
  })
})

describe('prompt extractor result window', () => {
  it('renders the compact frosted card shell', async () => {
    const requestPrompt = vi.fn().mockResolvedValueOnce({
      prompt: '一只坐在窗边的白猫，电影感光影，细腻毛发，柔和景深。',
      prompts: {
        'zh-CN': '一只坐在窗边的白猫，电影感光影，细腻毛发，柔和景深。',
        'en-US': 'a white cat by a window, cinematic light, detailed fur, soft depth of field.',
      },
      language: 'zh-CN',
      amountCents: 2,
      model: 'gemini-3.1-pro-preview',
    })

    render(
      <PromptResultApp
        initialJob={{
          id: 'job-1',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'zh-CN',
        }}
        requestPrompt={requestPrompt}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /提取提示词|Prompt Extractor/ })).toBeTruthy()
    })

    expect(screen.getByTestId('result-card').style.borderRadius).toBe('30px')
    expect(screen.getByRole('button', { name: /复制|Copy/ })).toBeTruthy()
    expect(screen.getByLabelText('prompt-output').textContent).toContain('白猫')
    expect(screen.getByText('Gemini 3.1 Pro')).toBeTruthy()
  })

  it('normalizes stored model aliases to the canonical Gemini 3.1 Pro label', () => {
    render(
      <PromptResultApp
        initialJob={{
          id: 'job-stored-model',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'zh-CN',
          prompt: '一只白猫',
          prompts: {
            'zh-CN': '一只白猫',
          },
          model: 'gemini-3.1-pro-preview',
        }}
        requestPrompt={vi.fn()}
      />,
    )

    expect(screen.getByText('Gemini 3.1 Pro')).toBeTruthy()
    expect(screen.queryByText('gemini-3.1-pro-preview')).toBeNull()
  })

  it('switches languages locally after one bilingual extraction request', async () => {
    const requestPrompt = vi.fn().mockResolvedValueOnce({
      prompt: '一只坐在窗边的白猫，电影感光影',
      prompts: {
        'zh-CN': '一只坐在窗边的白猫，电影感光影',
        'en-US': 'a white cat by the window, cinematic light',
      },
      language: 'zh-CN',
      amountCents: 2,
      model: 'gemini-3.1-pro-preview',
    })

    render(
      <PromptResultApp
        initialJob={{
          id: 'job-1',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'zh-CN',
        }}
        requestPrompt={requestPrompt}
      />,
    )

    await waitFor(() => {
      expect(requestPrompt).toHaveBeenCalledWith(
        'data:image/png;base64,ZmFrZQ==',
        'zh-CN',
      )
    })

    await userEvent.click(screen.getByRole('button', { name: 'English' }))

    await waitFor(() => {
      expect(screen.getByLabelText('prompt-output').textContent).toContain('white cat')
    })
    expect(requestPrompt).toHaveBeenCalledTimes(1)
  })

  it('keeps billing details hidden when amount values are returned', async () => {
    const requestPrompt = vi.fn().mockResolvedValueOnce({
      prompt: '一只白猫',
      prompts: {
        'zh-CN': '一只白猫',
        'en-US': 'a white cat',
      },
      language: 'zh-CN',
      amount: 3,
      model: 'gemini-3.1-pro-preview',
    })

    render(
      <PromptResultApp
        initialJob={{
          id: 'job-2',
          imageDataUrl: 'data:image/png;base64,ZmFrZQ==',
          locale: 'zh-CN',
        }}
        requestPrompt={requestPrompt}
      />,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('prompt-output').textContent).toContain('一只白猫')
    })
    expect(screen.queryByText(/计费信息|Usage/)).toBeNull()
    expect(screen.queryByText(/¥0.03/)).toBeNull()
  })
})
