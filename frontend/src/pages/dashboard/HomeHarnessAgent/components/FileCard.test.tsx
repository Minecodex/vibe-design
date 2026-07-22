import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FileCard } from './FileCard'

const fetchWorkspaceFileBlobMock = vi.fn()

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    fetchWorkspaceFileBlob: (...args: unknown[]) => fetchWorkspaceFileBlobMock(...args),
  },
  isHarnessWorkspaceRelativePath: (filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    return !!raw && !raw.startsWith('http://') && !raw.startsWith('https://') && !raw.startsWith('data:')
      && !raw.startsWith('blob:') && !raw.startsWith('/')
  },
  normalizeHarnessWorkspacePath: (filePath: string) =>
    String(filePath || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/^files\//, ''),
  resolveHarnessWorkspaceUrl: (
    _conversationId: string | number | null | undefined,
    filePath: string | null | undefined,
  ) => String(filePath || '').trim().replace(/\\/g, '/').replace(/^files\//, '') || undefined,
}))

describe('FileCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    fetchWorkspaceFileBlobMock.mockReset()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:workspace-preview'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('renders image workspace files as visible thumbnails instead of only a generic icon', () => {
    render(
      <FileCard
        file={{
          name: 'forest.png',
          path: 'forest.png',
          type: 'image',
          size: 1024,
          created_at: '2026-04-17T00:00:00Z',
        }}
        previewUrl="/agent/files/forest.png"
        isDark={false}
        onClick={vi.fn()}
      />,
    )

    const thumbnail = screen.getByAltText('forest.png') as HTMLImageElement
    expect(thumbnail).toBeInTheDocument()
    expect(thumbnail.src).toContain('/agent/files/forest.png')
  })

  it('renders video workspace files as playable previews', async () => {
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['video'], { type: 'video/mp4' }))

    render(
      <FileCard
        conversationId="conv-1"
        file={{
          name: 'clip.mp4',
          path: 'clip.mp4',
          type: 'video',
          size: 2048,
          created_at: '2026-04-17T00:00:00Z',
        }}
        previewUrl={undefined}
        isDark={false}
        onClick={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('conv-1', 'clip.mp4')
    })
    const preview = await screen.findByTestId('workspace-file-video-preview') as HTMLVideoElement
    expect(preview).toBeInTheDocument()
    expect(preview.getAttribute('src')).toBe('blob:workspace-preview')
  })

  it('resolves generated media sizes when the session file initially reports 0 B', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        headers: {
          get: () => null,
        },
      })
      .mockResolvedValueOnce({
        blob: async () => new Blob(['x'.repeat(2048)], { type: 'image/png' }),
      })

    vi.stubGlobal('fetch', fetchMock)

    render(
      <FileCard
        file={{
          name: 'generated.png',
          path: 'https://example.com/generated.png',
          type: 'image',
          size: 0,
          created_at: '2026-04-17T00:00:00Z',
        }}
        previewUrl="https://example.com/generated.png"
        isDark={false}
        onClick={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('2.0 KB')).toBeInTheDocument()
    })

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'https://example.com/generated.png', { method: 'HEAD' })
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'https://example.com/generated.png')
  })

  it.each([
    ['budget.xlsx', 'workspace-file-spreadsheet-icon', 'text-emerald-500'],
    ['brief.docx', 'workspace-file-document-icon', 'text-indigo-500'],
    ['deck.pptx', 'workspace-file-presentation-icon', 'text-rose-500'],
    ['landing.html', 'workspace-file-html-icon', 'text-purple-500'],
    ['notes.txt', 'workspace-file-text-icon', 'text-zinc-500'],
    ['script.py', 'workspace-file-code-icon', 'text-blue-500'],
  ])('renders %s with the matching homepage mode icon color', (name, testId, colorClass) => {
    render(
      <FileCard
        file={{
          name,
          path: name,
          type: 'other',
          size: 4096,
          created_at: '2026-04-17T00:00:00Z',
        }}
        previewUrl={undefined}
        isDark={false}
        onClick={vi.fn()}
      />,
    )

    expect(screen.getByTestId(testId)).toHaveClass(colorClass)
  })
})
