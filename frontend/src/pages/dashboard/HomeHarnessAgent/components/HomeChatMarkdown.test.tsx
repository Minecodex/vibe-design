import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomeChatMarkdown } from './HomeChatMarkdown'

const createWorkspacePreviewTokenMock = vi.fn()
const getWorkspacePreviewFileUrlMock = vi.fn()
const getHarnessGenerationArtifactTaskMock = vi.fn()

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    createWorkspacePreviewToken: (...args: unknown[]) => createWorkspacePreviewTokenMock(...args),
    getWorkspacePreviewFileUrl: (...args: unknown[]) => getWorkspacePreviewFileUrlMock(...args),
    getHarnessGenerationArtifactTask: (...args: unknown[]) => getHarnessGenerationArtifactTaskMock(...args),
  },
  isHarnessWorkspaceRelativePath: (value: string | null | undefined) => {
    const raw = String(value || '').trim()
    return !!raw && !/^(https?:|data:|blob:|\/)/.test(raw)
  },
  normalizeHarnessWorkspacePath: (value: string) => {
    let normalized = String(value || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/^sandbox:\/+/i, '')
    if (normalized.startsWith('code/files/')) {
      normalized = normalized.slice('code/files/'.length)
    } else if (normalized.startsWith('files/')) {
      normalized = normalized.slice('files/'.length)
    }
    if (normalized.startsWith('assets/inputs/')) {
      return `references/inputs/${normalized.slice('assets/inputs/'.length)}`
    }
    if (normalized.startsWith('assets/references/')) {
      return `references/generated/${normalized.slice('assets/references/'.length)}`
    }
    return normalized
  },
  isHtmlWorkspaceFilePath: (value: string | null | undefined) => {
    const normalized = String(value || '').trim().replace(/\\/g, '/')
    return normalized.endsWith('.html') || normalized.endsWith('.htm')
  },
  resolveHarnessWorkspaceUrl: (_conversationId: string | number | null | undefined, value: string | null | undefined) => value || undefined,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback: string | Record<string, unknown>, values?: Record<string, unknown>) => {
      if (key === 'homeHarness.media.generatingImageWithAlt') {
        return `Generating: ${String(values?.alt || '')}...`
      }
      if (key === 'homeHarness.media.generatingImage') {
        return 'Generating image...'
      }
      if (key === 'homeHarness.files.previewFile' && fallback && typeof fallback === 'object') {
        return `Preview file ${String(fallback.name || '')}`
      }
      if (key === 'homeHarness.artifactReference.previewArtifact' && fallback && typeof fallback === 'object') {
        return `Preview generated media ${String(fallback.name || '')}`
      }
      if (key === 'home.chat.generation_progress' && fallback && typeof fallback === 'object') {
        return `Progress ${String(fallback.progress || '')}%`
      }
      if (fallback && typeof fallback === 'object' && 'defaultValue' in fallback) {
        return String(fallback.defaultValue || '')
      }
      return fallback
    },
  }),
}))

const reportFile = {
  file_id: 'file-report',
  name: 'report.docx',
  path: 'references/sources/report.docx',
  type: 'document',
  size: 128,
  created_at: '2026-06-01T00:00:00.000Z',
  updated_at: null,
  current_version_id: '',
  versions: [],
  source: 'reference_asset',
} as any

const sheetFile = {
  file_id: 'file-sheet',
  name: 'budget.xlsx',
  path: 'references/sources/budget.xlsx',
  type: 'spreadsheet',
  size: 256,
  created_at: '2026-06-01T00:00:00.000Z',
  updated_at: null,
  current_version_id: '',
  versions: [],
  source: 'reference_asset',
} as any

const imageFile = {
  file_id: 'file-image',
  name: 'original.jpg',
  path: 'references/sources/web_image_001/original.jpg',
  type: 'image',
  size: 512,
  created_at: '2026-06-01T00:00:00.000Z',
  updated_at: null,
  current_version_id: '',
  versions: [],
  source: 'reference_asset',
} as any

const publishedWebBundleFile = {
  file_id: 'file-web-bundle',
  name: 'index.zip',
  path: 'published/file-web-bundle/v0001/source.zip',
  type: 'web',
  size: 7958,
  created_at: '2026-06-01T00:00:00.000Z',
  updated_at: null,
  current_version_id: 'v0001',
  current_version_path: 'published/file-web-bundle/v0001/source.zip',
  artifact_kind: 'web_bundle',
  artifact_metadata: {
    artifact_kind: 'web_bundle',
    bundle_format: 'zip',
    entry: 'index.html',
  },
  versions: [],
  source: 'generated',
} as any

describe('HomeChatMarkdown', () => {
  beforeEach(() => {
    createWorkspacePreviewTokenMock.mockReset()
    getWorkspacePreviewFileUrlMock.mockReset()
    getHarnessGenerationArtifactTaskMock.mockReset()

    createWorkspacePreviewTokenMock.mockResolvedValue({ preview_token: 'preview-token' })
    getWorkspacePreviewFileUrlMock.mockImplementation((conversationId: string, filePath: string, previewToken: string) =>
      `http://localhost:8000/api/v1/agent/harness/conversations/${conversationId}/preview-files/${encodeURIComponent(filePath)}?preview_token=${previewToken}`,
    )
    getHarnessGenerationArtifactTaskMock.mockResolvedValue({
      data: {
        task_id: 'task-image',
        artifact_ref: 'artifact_ref:generated-image-1',
        status: 'processing',
        kind: 'image',
        progress: 24,
        result_url: null,
        error_message: null,
      },
    })
  })

  it('opens markdown images in a fullscreen preview dialog when clicked', async () => {
    const user = userEvent.setup()

    render(
      <HomeChatMarkdown
        content="![Coffee](https://example.com/coffee.png)"
        isDark={false}
      />,
    )

    await user.click(screen.getByAltText('Coffee'))

    expect(await screen.findAllByAltText('Coffee')).toHaveLength(2)
  })

  it('loads workspace-relative markdown images through the preview-files API', async () => {
    render(
      <HomeChatMarkdown
        content="![Monkey](files/monkey_eating_grapes.png)"
        isDark={false}
        conversationId="conv-1"
      />,
    )

    const image = await screen.findByAltText('Monkey')

    expect(createWorkspacePreviewTokenMock).toHaveBeenCalledWith('conv-1')
    expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith('conv-1', 'monkey_eating_grapes.png', 'preview-token', { width: 1024 })
    expect(image).toHaveAttribute('src', 'http://localhost:8000/api/v1/agent/harness/conversations/conv-1/preview-files/monkey_eating_grapes.png?preview_token=preview-token')
  })

  it('loads code-root markdown images through the preview-files API', async () => {
    render(
      <HomeChatMarkdown
        content="![Monkey](code/monkey_eating_grapes.png)"
        isDark={false}
        conversationId="conv-1"
      />,
    )

    const image = await screen.findByAltText('Monkey')

    expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith('conv-1', 'code/monkey_eating_grapes.png', 'preview-token', { width: 1024 })
    expect(image).toHaveAttribute('src', 'http://localhost:8000/api/v1/agent/harness/conversations/conv-1/preview-files/code%2Fmonkey_eating_grapes.png?preview_token=preview-token')
  })

  it('canonicalizes legacy code/files markdown image paths before previewing', async () => {
    render(
      <HomeChatMarkdown
        content="![Monkey](code/files/monkey_eating_grapes.png)"
        isDark={false}
        conversationId="conv-1"
      />,
    )

    const image = await screen.findByAltText('Monkey')

    expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith('conv-1', 'monkey_eating_grapes.png', 'preview-token', { width: 1024 })
    expect(image).toHaveAttribute('src', 'http://localhost:8000/api/v1/agent/harness/conversations/conv-1/preview-files/monkey_eating_grapes.png?preview_token=preview-token')
  })

  it('renders generated image placeholders through i18n', async () => {
    render(
      <HomeChatMarkdown
        content="![Monkey](references/generated/monkey.png)"
        isDark={false}
        conversationId="conv-1"
      />,
    )

    expect(await screen.findByText('Generating: Monkey...')).toBeInTheDocument()
    expect(screen.queryByText(/生成中|图片生成中/)).not.toBeInTheDocument()
  })

  it('keeps root-relative markdown image URLs on the direct URL path', async () => {
    render(
      <HomeChatMarkdown
        content="![Upload](/api/v1/uploads/user-image.png)"
        isDark={false}
        conversationId="conv-1"
      />,
    )

    const image = await screen.findByAltText('Upload')

    expect(createWorkspacePreviewTokenMock).not.toHaveBeenCalled()
    expect(getWorkspacePreviewFileUrlMock).not.toHaveBeenCalled()
    expect(image).toHaveAttribute('src', '/api/v1/uploads/user-image.png')
  })

  it('reuses the preview-files URL inside the fullscreen preview dialog', async () => {
    const user = userEvent.setup()

    render(
      <HomeChatMarkdown
        content="![Monkey](files/monkey_eating_grapes.png)"
        isDark={false}
        conversationId="conv-1"
      />,
    )

    const image = await screen.findByAltText('Monkey')
    await user.click(image)

    const images = await screen.findAllByAltText('Monkey')
    const imageSources = images.map((image) => image.getAttribute('src'))
    expect(imageSources).toContain('http://localhost:8000/api/v1/agent/harness/conversations/conv-1/preview-files/monkey_eating_grapes.png?preview_token=preview-token')
    expect(createWorkspacePreviewTokenMock).toHaveBeenCalled()
  })

  it('renders markdown tables with visible cell borders', () => {
    render(
      <HomeChatMarkdown
        content={'| Name | Value |\n| --- | --- |\n| Foo | Bar |'}
        isDark={false}
      />,
    )

    const headerCell = screen.getByRole('columnheader', { name: 'Name' })
    const bodyCell = screen.getByRole('cell', { name: 'Foo' })

    expect(headerCell.style.border).toBe('1px solid var(--app-border)')
    expect(bodyCell.style.border).toBe('1px solid var(--app-border)')
  })

  it('renders final-answer bare workspace paths as file chips', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceFile = vi.fn()

    render(
      <HomeChatMarkdown
        content="本地预览: references/sources/report.docx。"
        isDark={false}
        workspaceFiles={[reportFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={onOpenWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file report.docx' }))

    expect(onOpenWorkspaceFile).toHaveBeenCalledWith(reportFile)
  })

  it('renders markdown links to workspace files as file chips', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceFile = vi.fn()

    render(
      <HomeChatMarkdown
        content="[本地预览](references/sources/report.docx)"
        isDark={false}
        workspaceFiles={[reportFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={onOpenWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file report.docx' }))

    expect(onOpenWorkspaceFile).toHaveBeenCalledWith(reportFile)
    expect(screen.queryByRole('link', { name: '本地预览' })).not.toBeInTheDocument()
  })

  it('renders inline code workspace paths as file chips', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceFile = vi.fn()

    render(
      <HomeChatMarkdown
        content="打开 `references/sources/budget.xlsx` 查看。"
        isDark={false}
        workspaceFiles={[sheetFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={onOpenWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file budget.xlsx' }))

    expect(onOpenWorkspaceFile).toHaveBeenCalledWith(sheetFile)
  })

  it('renders published web bundle zip paths as file chips', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceFile = vi.fn()

    render(
      <HomeChatMarkdown
        content="文件已发布：published/file-web-bundle/v0001/source.zip"
        isDark={false}
        workspaceFiles={[publishedWebBundleFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={onOpenWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file index.zip' }))

    expect(onOpenWorkspaceFile).toHaveBeenCalledWith(publishedWebBundleFile)
  })

  it('renders inline artifact refs as generated media chips', async () => {
    render(
      <HomeChatMarkdown
        content="`artifact_ref:generated-image-1`"
        isDark={false}
        conversationId="conv-1"
        enableArtifactReferences
      />,
    )

    expect(await screen.findByTestId('generation-artifact-reference')).toHaveTextContent('Generating image...')
    expect(getHarnessGenerationArtifactTaskMock).toHaveBeenCalledWith('conv-1', 'artifact_ref:generated-image-1')
  })

  it('does not refetch completed artifact refs with result URLs after remounting', async () => {
    getHarnessGenerationArtifactTaskMock.mockResolvedValue({
      data: {
        task_id: 'task-completed-image',
        artifact_ref: 'artifact_ref:completed-image-1',
        status: 'completed',
        kind: 'image',
        progress: 100,
        result_url: 'references/generated/completed-image.png',
        error_message: null,
      },
    })

    const props = {
      content: '`artifact_ref:completed-image-1`',
      isDark: false,
      conversationId: 'conv-1',
      enableArtifactReferences: true,
    }
    const { unmount } = render(<HomeChatMarkdown {...props} />)

    await waitFor(() => {
      expect(getHarnessGenerationArtifactTaskMock).toHaveBeenCalledTimes(1)
    })
    unmount()

    render(<HomeChatMarkdown {...props} />)

    await screen.findByTestId('generation-artifact-reference')
    expect(getHarnessGenerationArtifactTaskMock).toHaveBeenCalledTimes(1)
  })

  it('renders inline code image workspace paths as file chips', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceFile = vi.fn()

    render(
      <HomeChatMarkdown
        content="本地图片：`references/sources/web_image_003/original.jpg`"
        isDark={false}
        workspaceFiles={[{ ...imageFile, path: 'references/sources/web_image_003/original.jpg' }]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={onOpenWorkspaceFile}
      />,
    )

    expect(screen.getByText('Image')).toBeInTheDocument()
    expect(screen.queryByText('original.jpg')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Preview file original.jpg' }))

    expect(onOpenWorkspaceFile).toHaveBeenCalledWith(expect.objectContaining({
      path: 'references/sources/web_image_003/original.jpg',
    }))
  })

  it('matches inline code references against current version paths after refresh', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceFile = vi.fn()
    const versionedImageFile = {
      ...imageFile,
      path: 'published/file-image/v0001/original.jpg',
      current_version_path: 'references/sources/web_image_003/original.jpg',
    }

    render(
      <HomeChatMarkdown
        content="本地图片：`references/sources/web_image_003/original.jpg`"
        isDark={false}
        workspaceFiles={[versionedImageFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={onOpenWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file original.jpg' }))

    expect(onOpenWorkspaceFile).toHaveBeenCalledWith(versionedImageFile)
  })

  it('does not replace workspace paths inside fenced code blocks', () => {
    render(
      <HomeChatMarkdown
        content={'```text\nreferences/sources/report.docx\n```'}
        isDark={false}
        workspaceFiles={[reportFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Preview file report.docx' })).not.toBeInTheDocument()
    expect(screen.getByText('references/sources/report.docx')).toBeInTheDocument()
  })

  it('keeps markdown image references on the existing image preview path', async () => {
    render(
      <HomeChatMarkdown
        content="![Portrait](references/sources/web_image_001/original.jpg)"
        isDark={false}
        conversationId="conv-1"
        workspaceFiles={[imageFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={vi.fn()}
      />,
    )

    const image = await screen.findByAltText('Portrait')

    expect(image).toHaveAttribute('src', 'http://localhost:8000/api/v1/agent/harness/conversations/conv-1/preview-files/references%2Fsources%2Fweb_image_001%2Foriginal.jpg?preview_token=preview-token')
    expect(screen.queryByRole('button', { name: 'Preview file original.jpg' })).not.toBeInTheDocument()
  })

  it('does not replace external document links', () => {
    render(
      <HomeChatMarkdown
        content="[Doc](https://example.com/report.docx)"
        isDark={false}
        workspaceFiles={[reportFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={vi.fn()}
      />,
    )

    expect(screen.getByRole('link', { name: 'Doc' })).toHaveAttribute('href', 'https://example.com/report.docx')
    expect(screen.queryByRole('button', { name: 'Preview file report.docx' })).not.toBeInTheDocument()
  })

  it('does not replace ambiguous bare filenames', () => {
    const duplicateImageFile = {
      ...imageFile,
      file_id: 'file-image-2',
      path: 'references/sources/web_image_002/original.jpg',
    }

    render(
      <HomeChatMarkdown
        content="本地预览: original.jpg"
        isDark={false}
        workspaceFiles={[imageFile, duplicateImageFile]}
        enableWorkspaceFileReferences
        onOpenWorkspaceFile={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Preview file original.jpg' })).not.toBeInTheDocument()
    expect(screen.getByText(/original\.jpg/)).toBeInTheDocument()
  })
})
