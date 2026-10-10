function streamResponse(read: () => Promise<ReadableStreamReadResult<Uint8Array>>): Response {
  return new Response(new ReadableStream<Uint8Array>({
    async pull(controller) {
      const chunk = await read()
      if (chunk.done) controller.close()
      else controller.enqueue(chunk.value)
    },
  }))
}

import { beforeEach, describe, expect, it, vi } from 'vitest'

const { toastError } = vi.hoisted(() => ({
  toastError: vi.fn(),
}))

const { apiGetMock, apiPostMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    error: toastError,
  },
}))

vi.mock('../client', () => ({
  apiClient: {
    get: apiGetMock,
    post: apiPostMock,
  },
}))

vi.mock('@/config/runtimeConfig', () => ({
  getApiBaseUrl: () => 'https://example.com',
}))

import {
  agentApi,
  fetchSSE,
  resolveHarnessWorkspaceUrl,
  streamHarnessConversationEvents,
  streamHarnessRespondToAgent,
  streamHarnessRevisePlan,
  streamHarnessSendMessage,
  streamHarnessStartExecution,
} from './agent'

describe('fetchSSE', () => {
  beforeEach(() => {
    toastError.mockReset()
    vi.restoreAllMocks()
    localStorage.clear()
    apiGetMock.mockReset()
    apiPostMock.mockReset()
  })

  it('surfaces backend detail messages for failed streaming requests', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"detail":"积分不足，需要 40 积分"}', { status: 402 }))

    const iterator = fetchSSE('/agent/harness/conversations/conv-1/messages', { content: 'hello' })

    await expect(iterator.next()).rejects.toThrow('积分不足，需要 40 积分')
    expect(toastError).toHaveBeenCalledWith('积分不足，需要 40 积分')
  })

  it('fetches harness conversation detail snapshots', async () => {
    apiGetMock.mockResolvedValue({
      data: {
        id: 'conv-home-1',
        title: 'Harness detail',
        skill_id: null,
        mode: 'fast',
        model_preferences: {
          image_model: 'history-image',
          image_provider: 'builtin',
          video_model: 'history-video',
          video_provider: 'builtin',
          multimodal_model: 'history-chat',
          multimodal_provider: 'builtin',
          auto: false,
        },
        status: 'completed',
        runtime_status: 'idle',
        engine_version: 'harness',
        run_id: null,
        started_at: '2026-04-20T00:00:00.000Z',
        finished_at: '2026-04-20T00:10:00.000Z',
        pending_interaction: null,
        created_at: '2026-04-20T00:00:00.000Z',
        updated_at: '2026-04-20T00:10:00.000Z',
        runtime_state: {
          conversation_id: 'conv-home-1',
          phase: 'executing',
          run_status: 'waiting_input',
          user_interaction: {
            request_id: 'call_ask_1',
            question: 'Logo 基础规范确认',
            content: '### Gate D\n\n- 色彩标准应用\n- 响应式矩阵',
            kind: 'ask_user',
            status: 'pending',
            schema: {
              title: 'Logo 基础规范确认',
              submit_label: '确认并继续',
              fields: [
                {
                  id: 'logo_system_feedback',
                  label: '反馈',
                  type: 'textarea',
                },
              ],
            },
          },
        },
        messages: [
          {
            id: 'user-1',
            role: 'user',
            content: 'Analyze the image',
            created_at: '2026-04-20T00:00:01.000Z',
          },
        ],
      },
    })

    const response = await agentApi.getHarnessConversation('conv-home-1')

    expect(apiGetMock).toHaveBeenCalledWith(
      '/agent/harness/conversations/conv-home-1',
      { signal: undefined },
    )
    expect(response.data.messages).toEqual([
      expect.objectContaining({
        id: 'user-1',
        role: 'user',
        content: 'Analyze the image',
      }),
    ])
    expect(response.data.runtime_state?.user_interaction?.content).toBe(
      '### Gate D\n\n- 色彩标准应用\n- 响应式矩阵',
    )
    expect(response.data.model_preferences).toEqual({
      image_model: 'history-image',
      image_provider: 'builtin',
      video_model: 'history-video',
      video_provider: 'builtin',
      multimodal_model: 'history-chat',
      multimodal_provider: 'builtin',
      auto: false,
    })
  })

  it('streams harness events from the live stream endpoint', async () => {
    const event = {
      type: 'message_done',
      sequence: 13,
      run_id: null,
      data: {
        conversation_id: 'conv-home-1',
      },
    }
    const read = vi.fn()
      .mockResolvedValueOnce({
        done: false,
        value: new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
      })
      .mockResolvedValueOnce({
        done: true,
        value: undefined,
      })

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(read))

    const iterator = streamHarnessConversationEvents('conv-home-1')

    const next = await iterator.next()
    expect(next.done).toBe(false)
    expect(next.value).toMatchObject(event)

    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe('https://example.com/agent/harness/conversations/conv-home-1/stream')
    expect(init).toBeDefined()
    expect((init as RequestInit).method).toBe('GET')
  })

  it('streams harness conversation events from a durable sequence cursor', async () => {
    const read = vi.fn()
      .mockResolvedValueOnce({
        done: false,
        value: new TextEncoder().encode('data: {"type":"turn_completed","sequence":8}\n\n'),
      })
      .mockResolvedValueOnce({
        done: true,
        value: undefined,
      })

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(read))

    const iterator = streamHarnessConversationEvents('conv-home-1', 7)

    await expect(iterator.next()).resolves.toEqual({
      value: expect.objectContaining({ type: 'turn_completed', sequence: 8 }),
      done: false,
    })

    const [url] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe('https://example.com/agent/harness/conversations/conv-home-1/stream?after_sequence=7')
  })

  it('appends durable sequence cursors to POST harness streams', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => streamResponse(async () => ({ done: true, value: undefined })))

    await streamHarnessSendMessage('conv-home-1', { content: 'hello' }, undefined, 7).next()
    await streamHarnessRespondToAgent('conv-home-1', { request_id: 'req-1', answer: 'ok' }, undefined, 8).next()
    await streamHarnessStartExecution('conv-home-1', undefined, 9).next()
    await streamHarnessRevisePlan('conv-home-1', 'change it', undefined, 10).next()

    const urls = vi.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url))
    expect(urls).toEqual([
      'https://example.com/agent/harness/conversations/conv-home-1/messages?after_sequence=7',
      'https://example.com/agent/harness/conversations/conv-home-1/respond?after_sequence=8',
      'https://example.com/agent/harness/conversations/conv-home-1/plan/start?after_sequence=9',
      'https://example.com/agent/harness/conversations/conv-home-1/plan/revise?after_sequence=10',
    ])
  })

  it('opens a workspace office session', async () => {
    apiPostMock.mockResolvedValue({
      data: {
        session_id: 'office-session-1',
        file_path: 'spec.docx',
        file_kind: 'doc',
        engine: 'html',
        preview_file_path: 'code/docx-parser-html/index.html',
      },
    })

    const response = await agentApi.openWorkspaceOfficeSession('conv-home-1', {
      file_path: 'spec.docx',
    })

    expect(apiPostMock).toHaveBeenCalledWith(
      '/agent/harness/conversations/conv-home-1/office/open',
      { file_path: 'spec.docx' },
      { timeout: 60000 },
    )
    expect(response.data.session_id).toBe('office-session-1')
    expect(response.data.preview_file_path).toBe('code/docx-parser-html/index.html')
  })

  it('allows mark recognition requests to wait up to 60 seconds', async () => {
    apiPostMock.mockResolvedValue({ data: { labels: ['图标'] } })

    await agentApi.analyzeElement({
      image_url: '/assets/demo.png',
      relative_x: 0.25,
      relative_y: 0.5,
      language: 'zh',
    })

    expect(apiPostMock).toHaveBeenCalledWith(
      '/agent/harness/analyze-element',
      {
        image_url: '/assets/demo.png',
        relative_x: 0.25,
        relative_y: 0.5,
        language: 'zh',
      },
      { timeout: 60000 },
    )
  })

  it('closes a workspace office session', async () => {
    apiPostMock.mockResolvedValue({
      data: {
        session_id: 'office-session-1',
        closed: true,
      },
    })

    const response = await agentApi.closeWorkspaceOfficeSession('conv-home-1', {
      session_id: 'office-session-1',
    })

    expect(apiPostMock).toHaveBeenCalledWith(
      '/agent/harness/conversations/conv-home-1/office/close',
      { session_id: 'office-session-1' },
    )
    expect(response.data.closed).toBe(true)
  })

  it('resolves workspace urls using workspace-relative paths', () => {
    expect(resolveHarnessWorkspaceUrl('conv-home-1', 'files/assets/inputs/demo.png')).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/files/references%2Finputs%2Fdemo.png',
    )
    expect(resolveHarnessWorkspaceUrl('conv-home-1', 'sandbox:/references/generated/demo.png')).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/files/references%2Fgenerated%2Fdemo.png',
    )
    expect(resolveHarnessWorkspaceUrl('conv-home-1', 'assets/references/generated_image_001/original.png')).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/files/references%2Fgenerated%2Fgenerated_image_001%2Foriginal.png',
    )
    expect(resolveHarnessWorkspaceUrl('conv-home-1', 'references/inputs/demo.png')).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/files/references%2Finputs%2Fdemo.png',
    )
    expect(resolveHarnessWorkspaceUrl('conv-home-1', 'references/generated/generated_image_abc/original.png')).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/files/references%2Fgenerated%2Fgenerated_image_abc%2Foriginal.png',
    )
  })

  it('builds workspace file urls with encoded workspace paths', () => {
    expect(agentApi.getWorkspaceFileUrl('conv-home-1', 'file_versions/report.md')).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/files/file_versions%2Freport.md',
    )
  })

  it('keeps the download filename suffix in version preview urls', () => {
    expect(agentApi.getWorkspacePreviewFileVersionUrl(
      'conv-home-1',
      'f_ppt',
      'v0001',
      'preview-token',
      '侘寂风格设计美学.pptx',
    )).toBe(
      'https://example.com/agent/harness/conversations/conv-home-1/preview-file-version/f_ppt/v0001/%E4%BE%98%E5%AF%82%E9%A3%8E%E6%A0%BC%E8%AE%BE%E8%AE%A1%E7%BE%8E%E5%AD%A6.pptx?preview_token=preview-token',
    )
  })
})
