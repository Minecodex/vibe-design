import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GenerationCard } from './GenerationCard'

const getWorkspaceFileUrlMock = vi.fn()
const fetchWorkspaceFileBlobMock = vi.fn()
const getHarnessGenerationTaskMock = vi.fn()
const createWorkspacePreviewTokenMock = vi.fn()
const getWorkspacePreviewFileUrlMock = vi.fn()
let currentLanguage = 'en-US'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string | { defaultValue?: string; progress?: number }, options?: { progress?: number }) => {
      const payload = typeof fallback === 'object' ? fallback : options
      const progress = payload?.progress ?? 0
      if (key === 'home.chat.generation_progress') {
        return currentLanguage.startsWith('zh') ? `进度 ${progress}%` : `Progress ${progress}%`
      }
      if (typeof fallback === 'string') {
        return fallback
      }
      return key
    },
    i18n: {
      language: currentLanguage,
      resolvedLanguage: currentLanguage,
    },
  }),
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getWorkspaceFileUrl: (...args: unknown[]) => getWorkspaceFileUrlMock(...args),
    fetchWorkspaceFileBlob: (...args: unknown[]) => fetchWorkspaceFileBlobMock(...args),
    getHarnessGenerationTask: (...args: unknown[]) => getHarnessGenerationTaskMock(...args),
    createWorkspacePreviewToken: (...args: unknown[]) => createWorkspacePreviewTokenMock(...args),
    getWorkspacePreviewFileUrl: (...args: unknown[]) => getWorkspacePreviewFileUrlMock(...args),
  },
  isHarnessWorkspaceRelativePath: (filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    return !!raw && !raw.startsWith('http://') && !raw.startsWith('https://') && !raw.startsWith('data:')
      && !raw.startsWith('blob:') && !raw.startsWith('/')
  },
  normalizeHarnessWorkspacePath: (filePath: string) =>
    String(filePath || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/^files\//, ''),
  resolveHarnessWorkspaceUrl: (
    conversationId: string | number | null | undefined,
    filePath: string | null | undefined,
  ) => {
    const normalized = String(filePath || '').trim().replace(/\\/g, '/').replace(/^files\//, '')
    if (!normalized || normalized.startsWith('http://') || normalized.startsWith('https://') || normalized.startsWith('/')) {
      return normalized || undefined
    }
    if (conversationId == null || conversationId === '') {
      return normalized
    }
    return getWorkspaceFileUrlMock(String(conversationId), normalized)
  },
}))

function mockVideoPlaybackApis() {
  const playMock = vi.fn().mockResolvedValue(undefined)
  const pauseMock = vi.fn()

  Object.defineProperty(HTMLMediaElement.prototype, 'play', {
    configurable: true,
    writable: true,
    value: playMock,
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    writable: true,
    value: pauseMock,
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
    configurable: true,
    get() {
      return 0
    },
    set() {},
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'duration', {
    configurable: true,
    get() {
      return 5
    },
  })
}

describe('GenerationCard', () => {
  beforeEach(() => {
    currentLanguage = 'en-US'
    getWorkspaceFileUrlMock.mockReset()
    fetchWorkspaceFileBlobMock.mockReset()
    getHarnessGenerationTaskMock.mockReset()
    createWorkspacePreviewTokenMock.mockReset()
    getWorkspacePreviewFileUrlMock.mockReset()
    createWorkspacePreviewTokenMock.mockResolvedValue({ preview_token: 'tok-test', expires_in_seconds: 600 })
    getWorkspacePreviewFileUrlMock.mockImplementation(
      (conversationId: string, filePath: string, token: string) =>
        `/preview-files/${conversationId}/${filePath}?preview_token=${token}`,
    )
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:generated-video'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('resolves local workspace media paths to harness file URLs', async () => {
    mockVideoPlaybackApis()

    const { container } = render(
      <GenerationCard
        conversationId="conv-77"
        taskId={77}
        status="completed"
        mediaType="video"
        toolName="generate_video"
        resultUrl="generated/waves.mp4"
        modelLabel="Kling 2.6"
        duration="5"
        aspectRatio="16:9"
        isDark={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Toggle generation 77' }))

    await waitFor(() => {
      expect(createWorkspacePreviewTokenMock).toHaveBeenCalledWith('conv-77')
    })
    await waitFor(() => {
      expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith('conv-77', 'generated/waves.mp4', 'tok-test', { width: 1024 })
    })
    await waitFor(() => {
      expect(container.querySelector('video')?.getAttribute('src')).toBe(
        '/preview-files/conv-77/generated/waves.mp4?preview_token=tok-test',
      )
    })
  })

  it('renders completed video cards with the canvas-style preview chrome', async () => {
    mockVideoPlaybackApis()

    const { container } = render(
      <GenerationCard
        taskId={99}
        status="completed"
        mediaType="video"
        toolName="generate_video"
        resultUrl="https://example.com/waves.mp4"
        modelLabel="Kling 2.6"
        duration="5"
        aspectRatio="16:9"
        isDark={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Toggle generation 99' }))

    expect(screen.getByLabelText('Play video preview')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-video-item')).toBeInTheDocument()
    expect(container.querySelector('video')?.hasAttribute('controls')).toBe(false)
  })

  it('opens the modal when the image generation card body is clicked', async () => {
    render(
      <GenerationCard
        taskId={12}
        status="completed"
        mediaType="image"
        toolName="generate_image"
        resultUrl="https://example.com/generated.png"
        prompt="A calm landscape"
        isDark={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Toggle generation 12' }))
    fireEvent.click(screen.getByRole('button', { name: 'A calm landscape' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByAltText('A calm landscape')).toBeInTheDocument()
  })

  it('lets completed image generations be reused as composer references', async () => {
    const onUseAsReference = vi.fn()

    render(
      <GenerationCard
        taskId={121}
        status="completed"
        mediaType="image"
        toolName="generate_image"
        resultUrl="references/generated/generated_image_001/original.png"
        prompt="A calm landscape"
        onUseAsReference={onUseAsReference}
        isDark={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Toggle generation 121' }))
    fireEvent.click(screen.getByRole('button', { name: 'Use as reference' }))

    expect(onUseAsReference).toHaveBeenCalledWith({
      type: 'image',
      url: 'references/generated/generated_image_001/original.png',
      name: 'original.png',
    })
  })

  it('does not expose image reference reuse for completed video generations', async () => {
    mockVideoPlaybackApis()

    render(
      <GenerationCard
        taskId={122}
        status="completed"
        mediaType="video"
        toolName="generate_video"
        resultUrl="references/generated/generated_video_001/original.mp4"
        onUseAsReference={vi.fn()}
        isDark={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Toggle generation 122' }))

    expect(screen.queryByRole('button', { name: 'Use as reference' })).not.toBeInTheDocument()
  })

  it('shows localized progress text while generation is still running', async () => {
    getHarnessGenerationTaskMock.mockResolvedValue({
      data: {
        task_id: 135,
        status: 'running',
        progress: 42,
        result_url: null,
        error_message: null,
      },
    })

    const { rerender } = render(
      <GenerationCard
        conversationId="conv-135"
        taskId={135}
        status="running"
        mediaType="video"
        toolName="generate_video"
        modelLabel="Seedance 1.5 Pro"
        isDark={false}
      />,
    )

    expect(await screen.findByText('Progress 42%')).toBeInTheDocument()

    currentLanguage = 'zh-CN'
    rerender(
      <GenerationCard
        conversationId="conv-135"
        taskId={135}
        status="running"
        mediaType="video"
        toolName="generate_video"
        modelLabel="Seedance 1.5 Pro"
        isDark={false}
      />,
    )

    expect(await screen.findByText('进度 42%')).toBeInTheDocument()
  })

  it('renders model aliases when only a suffixed raw model name is available', () => {
    render(
      <GenerationCard
        taskId={188}
        status="completed"
        mediaType="image"
        toolName="generate_image"
        resultUrl="https://example.com/monkey.png"
        modelName="doubao-seedream-4-5-251128"
        isDark={false}
      />,
    )

    expect(screen.getByText('Seedream 4.5')).toBeInTheDocument()
    expect(screen.queryByText('doubao-seedream-4-5-251128')).not.toBeInTheDocument()
  })

  it('recovers a failed harness card back to running when polling reports an in-flight retry', async () => {
    getHarnessGenerationTaskMock.mockResolvedValue({
      data: {
        task_id: 501,
        status: 'processing',
        progress: 18,
        result_url: null,
        error_message: null,
      },
    })

    render(
      <GenerationCard
        conversationId="conv-501"
        taskId={501}
        status="failed"
        mediaType="image"
        toolName="generate_image"
        errorMessage="Generation failed"
        isDark={false}
      />,
    )

    expect(await screen.findByText('Progress 18%')).toBeInTheDocument()
    expect(screen.queryByText('Generation failed')).not.toBeInTheDocument()
  })

  it('uses generation task artifact relative paths when polling completes', async () => {
    getHarnessGenerationTaskMock.mockResolvedValue({
      data: {
        task_id: 246,
        status: 'completed',
        progress: 100,
        result_url: null,
        artifact: {
          absolute_path: '/app/uploads/harness/users/1/conversations/conv-246/files/generated/image.png',
          relative_path: 'generated/image.png',
          base_dir: 'FILES_DIR',
        },
        error_message: null,
      },
    })

    render(
      <GenerationCard
        conversationId="conv-246"
        taskId={246}
        status="running"
        mediaType="image"
        toolName="generate_image"
        modelLabel="Nano Banana 2"
        isDark={false}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Toggle generation 246' }))

    await waitFor(() => {
      expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith('conv-246', 'generated/image.png', 'tok-test', { width: 512 })
    })
  })
})
