import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  updateToolCallMock,
  onCanvasUpdateMock,
  getHarnessGenerationTaskMock,
  queryTaskMock,
} = vi.hoisted(() => ({
  updateToolCallMock: vi.fn(),
  onCanvasUpdateMock: vi.fn(),
  getHarnessGenerationTaskMock: vi.fn(),
  queryTaskMock: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}))

vi.mock('@/store/canvasAgentStore', () => ({
  useChatStore: (selector: (state: any) => any) =>
    selector({
      conversationId: 101,
      engineVersion: 'harness',
      updateToolCall: updateToolCallMock,
      onCanvasUpdate: onCanvasUpdateMock,
    }),
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getHarnessGenerationTask: getHarnessGenerationTaskMock,
  },
  isHarnessWorkspaceRelativePath: (filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    return raw.length > 0 && !/^(?:https?:|data:|blob:|\/)/.test(raw)
  },
  normalizeHarnessWorkspacePath: (filePath: string) => String(filePath || '').trim(),
}))

vi.mock('@/api/endpoints/generation', () => ({
  generationApi: {
    queryTask: queryTaskMock,
  },
}))

vi.mock('../generationPolling', () => ({
  startSerialPolling: vi.fn(() => vi.fn()),
}))

import { GenerationTaskBox } from './GenerationTaskBox'

describe('GenerationTaskBox', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders completed generation media with requested resolution until real dimensions load', () => {
    const { container } = render(
      <GenerationTaskBox
        toolCall={{
          callId: 'functions.generate_image:0',
          name: 'generate_image',
          args: {},
          status: 'completed',
          result: {
            task_id: 42,
            status: 'completed',
            result_url: '/api/v1/uploads/generated/image.png',
            model_name: 'gpt-image-2',
            model_label: 'GPT-Image 2',
            provider_code: 'builtin',
            task_snapshot_loaded: true,
            params: {
              resolution: '1K',
              aspect_ratio: '1:1',
            },
          },
        } as any}
        isDark={false}
        messageId="assistant-1"
        onPreview={vi.fn()}
        onDownload={vi.fn()}
      />,
    )

    expect(container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/api/v1/uploads/generated/image.png'))
    expect(screen.getByText('GPT-Image 2')).toBeInTheDocument()
    expect(screen.getByText('1K')).toBeInTheDocument()
    expect(screen.queryByText('1024×1024')).not.toBeInTheDocument()
    expect(getHarnessGenerationTaskMock).not.toHaveBeenCalled()
    expect(queryTaskMock).not.toHaveBeenCalled()
  })

  it('renders actual image dimensions after completed media loads', () => {
    const { container } = render(
      <GenerationTaskBox
        toolCall={{
          callId: 'functions.generate_image:0',
          name: 'generate_image',
          args: {},
          status: 'completed',
          result: {
            task_id: 42,
            status: 'completed',
            result_url: '/api/v1/uploads/generated/image.png',
            model_name: 'gpt-image-2',
            model_label: 'GPT-Image 2',
            provider_code: 'builtin',
            task_snapshot_loaded: true,
            params: {
              resolution: '4K',
              aspect_ratio: '1:1',
            },
          },
        } as any}
        isDark={false}
        messageId="assistant-1"
        onPreview={vi.fn()}
        onDownload={vi.fn()}
      />,
    )

    const image = container.querySelector('img')!
    expect(screen.getByText('4K')).toBeInTheDocument()
    Object.defineProperty(image, 'naturalWidth', { configurable: true, value: 2880 })
    Object.defineProperty(image, 'naturalHeight', { configurable: true, value: 2880 })
    fireEvent.load(image)

    expect(screen.getByText('2880×2880')).toBeInTheDocument()
    expect(screen.queryByText('4096×4096')).not.toBeInTheDocument()
  })

  it('syncs canvas revision before inserting a running generation placeholder', () => {
    render(
      <GenerationTaskBox
        toolCall={{
          callId: 'functions.generate_image:placeholder',
          name: 'generate_image',
          args: {},
          status: 'running',
          result: {
            task_id: 42,
            status: 'processing',
            canvas_revision: 17,
            canvas_item: {
              id: 'canvas-placeholder-42',
              type: 'image_generator',
              task_id: 42,
              status: 'generating',
              url: '',
            },
          },
        } as any}
        isDark={false}
        messageId="assistant-1"
        onPreview={vi.fn()}
        onDownload={vi.fn()}
      />,
    )

    expect(onCanvasUpdateMock).toHaveBeenNthCalledWith(
      1,
      'sync_canvas_revision',
      {},
      { canvasRevision: 17, canvasItemDeleted: false },
    )
    expect(onCanvasUpdateMock).toHaveBeenNthCalledWith(
      2,
      'add',
      expect.objectContaining({
        id: 'canvas-placeholder-42',
        type: 'image_generator',
        status: 'generating',
        canvas_revision: 17,
        canvas_item_deleted: undefined,
      }),
    )
  })
})
