import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import './index.testSetup'
import { ChatHomePage } from './index'
import {
  createXlsxBase64Workbook,
  createWorkspacePreviewTokenMock,
  fetchWorkspaceFileBlobMock,
  fetchWorkspaceFileVersionBlobMock,
  fetchWorkspaceHtmlBundleBlobMock,
  getWorkspaceHtmlPreviewUrlMock,
  getWorkspaceHtmlVersionPreviewUrlMock,
  getWorkspacePreviewFileUrlMock,
  getWorkspacePreviewFileVersionUrlMock,
  latestSheetEditorSnapshot,
  openWorkspaceOfficeSessionMock,
  saveWorkspaceOfficeSessionMock,
  storeState,
  uploadAttachmentMock,
} from './index.testSetup'
describe('ChatHomePage previews', () => {
  it('opens markdown session files in the side preview panel and hides history while previewing', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['Todo preview body'], { type: 'text/markdown' }))
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-md-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-19T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'TODO.md',
          path: 'TODO.md',
          type: 'text',
          size: 64,
          created_at: '2026-04-19T09:59:00Z',
        },
      ],
    })

    const { container } = render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('TODO.md'))

    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('42', 'TODO.md')
    })
    expect(screen.getByTestId('home-chat-markdown-preview')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="home-chat-history-scroll"]')).not.toBeInTheDocument()
  })

  it('opens plain text session files in the side preview panel', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue({
      text: async () => 'line one\n{"ok": true}',
    } as Blob)
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-text-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-19T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'notes.txt',
          path: 'notes.txt',
          type: 'text',
          size: 64,
          created_at: '2026-04-19T09:59:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('notes.txt'))

    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('42', 'notes.txt')
    })
    expect(screen.getByTestId('home-chat-text-preview')).toBeInTheDocument()
    expect(await screen.findByText(/line one/)).toBeInTheDocument()
    expect(screen.getByText(/\{"ok": true\}/)).toBeInTheDocument()
  })

  it('opens workspace images in a fullscreen preview dialog when clicked from the files modal', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-image-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'forest.png',
          path: 'forest.png',
          type: 'image',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('forest.png'))

    const preview = await screen.findByAltText('forest.png')
    expect(preview).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('42', 'forest.png')
    })
    expect(preview.getAttribute('src')).toBe('blob:workspace-media')
  })

  it('opens workspace videos in a player dialog when clicked from the files modal', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['video'], { type: 'video/mp4' }))
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-video-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'clip.mp4',
          path: 'clip.mp4',
          type: 'video',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('clip.mp4'))

    const preview = await screen.findByTestId('home-chat-video-preview')
    expect(preview).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('42', 'clip.mp4')
    })
    expect(preview.getAttribute('src')).toBe('blob:workspace-media')
  })

  it('opens html workspace files in the side preview rail with an iframe', async () => {
    const user = userEvent.setup()
    createWorkspacePreviewTokenMock.mockResolvedValue({ preview_token: 'preview-token' })
    getWorkspaceHtmlPreviewUrlMock.mockImplementation(
      (_conversationId: string, filePath: string, previewToken: string) =>
        `/agent/harness/conversations/42/preview-html/${filePath}?preview_token=${previewToken}`,
    )
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-html-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'landing.html',
          path: 'landing.html',
          type: 'web',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('landing.html'))

    const rail = await screen.findByTestId('home-chat-html-preview')
    const mainPanel = screen.getByTestId('home-chat-message-scroll').parentElement
    const layoutRow = rail.parentElement
    const iframe = screen.getByTitle('landing.html') as HTMLIFrameElement
    expect(mainPanel?.className).toContain('md:w-[980px]')
    expect(mainPanel?.className).not.toContain('flex-1')
    expect(layoutRow?.className).toContain('max-w-none')
    expect(layoutRow?.className).not.toContain('mx-auto')
    expect(layoutRow?.className).not.toContain('max-w-[1840px]')
    expect(rail).toBeInTheDocument()
    expect(rail.className).toContain('flex-1')
    expect(rail.className).not.toContain('w-[900px]')
    expect(iframe).toBeInTheDocument()
    await waitFor(() => {
      expect(createWorkspacePreviewTokenMock).toHaveBeenCalledWith('42')
    })
    expect(iframe.getAttribute('src')).toBe('/agent/harness/conversations/42/preview-html/landing.html?preview_token=preview-token')
  })

  it('opens published web bundle zip files in the side preview rail with an iframe', async () => {
    const user = userEvent.setup()
    createWorkspacePreviewTokenMock.mockResolvedValue({ preview_token: 'preview-token' })
    getWorkspaceHtmlVersionPreviewUrlMock.mockImplementation(
      (_conversationId: string, fileId: string, versionId: string, previewToken: string) =>
        `/agent/harness/conversations/42/preview-html-version/${fileId}/${versionId}?preview_token=${previewToken}`,
    )
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-web-bundle-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          file_id: 'f_8b40f57dbc',
          name: 'index.zip',
          path: 'published/f_8b40f57dbc/v0001/source.zip',
          type: 'web',
          size: 19843,
          created_at: '2026-05-06T05:08:25Z',
          current_version_id: 'v0001',
          artifact_kind: 'web_bundle',
          artifact_metadata: {
            artifact_kind: 'web_bundle',
            bundle_format: 'zip',
            entry: 'index.html',
          },
          versions: [
            {
              version_id: 'v0001',
              label: 'Version 1',
              size: 19843,
              sha256: 'abc',
              created_at: '2026-05-06T05:08:25Z',
              created_by: 'agent',
              artifact_metadata: {
                artifact_kind: 'web_bundle',
                bundle_format: 'zip',
                entry: 'index.html',
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('index.zip'))

    const rail = await screen.findByTestId('home-chat-html-preview')
    const iframe = screen.getByTitle('index.zip') as HTMLIFrameElement
    expect(rail).toBeInTheDocument()
    expect(iframe).toBeInTheDocument()
    await waitFor(() => {
      expect(createWorkspacePreviewTokenMock).toHaveBeenCalledWith('42')
    })
    expect(getWorkspaceHtmlVersionPreviewUrlMock).toHaveBeenCalledWith(
      '42',
      'f_8b40f57dbc',
      'v0001',
      'preview-token',
    )
    expect(iframe.getAttribute('src')).toBe('/agent/harness/conversations/42/preview-html-version/f_8b40f57dbc/v0001?preview_token=preview-token')
  })

  it('opens published web bundle zip files in a browser tab through the html preview endpoint', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    createWorkspacePreviewTokenMock.mockResolvedValue({ preview_token: 'preview-token' })
    getWorkspaceHtmlVersionPreviewUrlMock.mockImplementation(
      (_conversationId: string, fileId: string, versionId: string, previewToken: string) =>
        `/agent/harness/conversations/42/preview-html-version/${fileId}/${versionId}?preview_token=${previewToken}`,
    )
    getWorkspacePreviewFileVersionUrlMock.mockImplementation(
      (_conversationId: string, fileId: string, versionId: string, previewToken: string, fileName?: string) =>
        `/agent/harness/conversations/42/preview-file-version/${fileId}/${versionId}/${fileName}?preview_token=${previewToken}`,
    )
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-web-bundle-open-external',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          file_id: 'f_8b40f57dbc',
          name: 'index.zip',
          path: 'published/f_8b40f57dbc/v0001/source.zip',
          type: 'web',
          size: 19843,
          created_at: '2026-05-06T05:08:25Z',
          current_version_id: 'v0001',
          artifact_kind: 'web_bundle',
          artifact_metadata: {
            artifact_kind: 'web_bundle',
            bundle_format: 'zip',
            entry: 'index.html',
          },
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('index.zip'))
    await screen.findByTestId('home-chat-html-preview')

    await user.click(screen.getByRole('button', { name: 'home.chat.open_external' }))

    await waitFor(() => {
      expect(getWorkspaceHtmlVersionPreviewUrlMock).toHaveBeenCalledWith(
        '42',
        'f_8b40f57dbc',
        'v0001',
        'preview-token',
      )
    })
    expect(getWorkspacePreviewFileVersionUrlMock).not.toHaveBeenCalled()
    expect(openSpy).toHaveBeenCalledWith(
      '/agent/harness/conversations/42/preview-html-version/f_8b40f57dbc/v0001?preview_token=preview-token',
      '_blank',
      'noopener,noreferrer',
    )
    openSpy.mockRestore()
  })

  it('opens docx workspace files in the office rail with save controls', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-doc-session',
        file_path: 'spec.docx',
        file_kind: 'doc',
        engine: 'html',
        preview_file_path: '.agent/preview_cache/docx-parser-html/index.html',
        readonly: true,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-docx-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'spec.docx',
          path: 'spec.docx',
          type: 'text',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('spec.docx'))

    expect(await screen.findByTestId('home-chat-doc-html-preview')).toHaveTextContent('.agent/preview_cache/docx-parser-html/index.html')
    expect(screen.queryByRole('button', { name: 'Save spec.docx' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Localized Download' })).toBeInTheDocument()
    expect(openWorkspaceOfficeSessionMock).toHaveBeenCalledWith('42', { file_path: 'spec.docx' })
  })

  it('opens xlsx workspace files from source blobs and merges backend warnings into the workbook snapshot', async () => {
    const user = userEvent.setup()
    const sourceBlob = await createXlsxBase64Workbook()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-session',
        file_path: 'budget.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-1',
        source_blob: sourceBlob,
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        warnings: ['Pivot tables are read-only in this preview.'],
        capabilities: {
          detected_unsupported_features: [],
        },
        readonly: false,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'budget.xlsx',
          path: 'budget.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('budget.xlsx'))

    expect(await screen.findByTestId('home-chat-univer-sheet-editor')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save budget.xlsx' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Localized Download' })).toBeInTheDocument()
    expect(openWorkspaceOfficeSessionMock).toHaveBeenCalledWith('42', { file_path: 'budget.xlsx' })
    expect(latestSheetEditorSnapshot).toMatchObject({
      kind: 'sheet',
      sheetOrder: ['sheet-1'],
      activeSheetId: 'sheet-1',
      warning: 'Pivot tables are read-only in this preview.',
      sheets: {
        'sheet-1': {
          id: 'sheet-1',
          name: 'Budget',
          cells: {
            '0:0': { v: 'Item', t: 's' },
            '1:1': { v: 18, t: 'n' },
          },
          freeze: {
            rowSplit: 1,
            colSplit: 0,
          },
        },
      },
    })
  })

  it('shows an office preview error instead of a loading spinner when opening an xlsx preview fails', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-session',
        file_path: 'budget.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-1',
        source_blob: 'not-a-valid-xlsx',
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        warnings: [],
        capabilities: {
          detected_unsupported_features: [],
        },
        readonly: false,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-preview-error',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'budget.xlsx',
          path: 'budget.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('budget.xlsx'))

    expect(await screen.findByText('Failed to open office preview.')).toBeInTheDocument()
    expect(screen.queryByText('Opening sheet session...')).not.toBeInTheDocument()
  })

  it('falls back to the backend sheet snapshot when exceljs cannot parse the source blob', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-session-fallback',
        file_path: 'budget.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-fallback',
        source_blob: 'not-a-valid-xlsx',
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        snapshot: {
          kind: 'sheet',
          sheets: [
            {
              id: 'sheet-backend-1',
              name: 'Budget',
              rows: {
                0: { h: 32 },
              },
              cols: {
                1: { w: 120 },
              },
              cells: {
                '0:0': { v: 'Item', t: 's' },
                '1:1': { v: 18, t: 'n' },
              },
              merges: [],
              freeze: {
                rowSplit: 1,
                colSplit: 0,
              },
            },
          ],
          styles: {},
        },
        warnings: ['Preview loaded from backend snapshot.'],
        capabilities: {
          detected_unsupported_features: [],
        },
        readonly: false,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-preview-fallback',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'budget.xlsx',
          path: 'budget.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('budget.xlsx'))

    expect(await screen.findByTestId('home-chat-univer-sheet-editor')).toBeInTheDocument()
    expect(screen.queryByText('Failed to open office preview.')).not.toBeInTheDocument()
    expect(latestSheetEditorSnapshot).toMatchObject({
      kind: 'sheet',
      sheetOrder: ['sheet-backend-1'],
      activeSheetId: 'sheet-backend-1',
      warning: 'Preview loaded from backend snapshot.',
      sheets: {
        'sheet-backend-1': {
          id: 'sheet-backend-1',
          name: 'Budget',
          rows: {
            0: { h: 32 },
          },
          cols: {
            1: { w: 120 },
          },
          cells: {
            '0:0': { v: 'Item', t: 's' },
            '1:1': { v: 18, t: 'n' },
          },
          freeze: {
            rowSplit: 1,
            colSplit: 0,
          },
        },
      },
    })
  })

  it('opens pptx workspace files in the office rail without save controls', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-presentation-session',
        file_path: 'deck.pptx',
        file_kind: 'presentation',
        engine: 'html',
        preview_file_path: '.agent/preview_cache/ppt-parser-html/index.html',
        readonly: true,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-pptx-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'deck.pptx',
          path: 'deck.pptx',
          type: 'presentation',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('deck.pptx'))

    expect(await screen.findByTestId('home-chat-doc-html-preview')).toHaveTextContent('.agent/preview_cache/ppt-parser-html/index.html')
    expect(screen.queryByRole('button', { name: 'Save deck.pptx' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Localized Download' })).toBeInTheDocument()
    expect(openWorkspaceOfficeSessionMock).toHaveBeenCalledWith('42', { file_path: 'deck.pptx' })
  })

  it('sends a normal homepage message when regenerating a ppt slide from preview', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-presentation-session',
        file_path: 'deck.pptx',
        file_kind: 'presentation',
        engine: 'html',
        preview_file_path: '.agent/preview_cache/ppt-parser-html/index.html',
        readonly: true,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-pptx-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'deck.pptx',
          path: 'deck.pptx',
          type: 'presentation',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })
    storeState.sendMessage.mockResolvedValue(undefined)

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('deck.pptx'))
    await user.click(await screen.findByTestId('home-chat-doc-html-preview-regenerate-slide-2'))

    await waitFor(() => {
      expect(storeState.sendMessage).toHaveBeenCalledWith(
        'Help me regenerate slide 2 in the PPT',
        undefined,
        expect.objectContaining({
          modelPreferences: expect.objectContaining({
            image_model: 'img-fast',
            image_provider: 'builtin',
            video_model: 'vid-fast',
            video_provider: 'builtin',
            multimodal_model: 'mm-fast',
            multimodal_provider: 'builtin',
          }),
          actionType: 'presentation_regenerate_slide',
        }),
      )
    })
  })

  it('disables ppt slide regenerate actions while the homepage agent is busy', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-presentation-session',
        file_path: 'deck.pptx',
        file_kind: 'presentation',
        engine: 'html',
        preview_file_path: '.agent/preview_cache/ppt-parser-html/index.html',
        readonly: true,
      },
    })
    Object.assign(storeState, {
      isStreaming: true,
      runStatus: 'running',
      messages: [
        {
          id: 'assistant-pptx-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'deck.pptx',
          path: 'deck.pptx',
          type: 'presentation',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('deck.pptx'))

    expect(await screen.findByTestId('home-chat-doc-html-preview-regenerate-slide-2')).toBeDisabled()
  })

  it('opens xlsx sheets without save controls', async () => {
    const user = userEvent.setup()
    const sourceBlob = await createXlsxBase64Workbook()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-session',
        file_path: 'budget.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-1',
        source_blob: sourceBlob,
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        warnings: ['Pivot tables are read-only in this preview.'],
        capabilities: {
          detected_unsupported_features: [],
        },
        readonly: false,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-save-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'budget.xlsx',
          path: 'budget.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('budget.xlsx'))

    expect(await screen.findByTestId('home-chat-univer-sheet-editor')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save budget.xlsx' })).not.toBeInTheDocument()
    expect(saveWorkspaceOfficeSessionMock).not.toHaveBeenCalled()
  })

  it('opens xlsx html previews when the office session includes a rendered preview path', async () => {
    const user = userEvent.setup()
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-chart-session',
        file_path: 'chart.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-chart',
        preview_file_path: '.agent/preview_cache/xlsx-parser-html/chart-cache/index.html',
        source_blob: 'base64-is-not-needed-for-html-preview',
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        warnings: ['检测到图表，已使用 HTML 预览渲染。'],
        capabilities: {
          detected_unsupported_features: ['charts'],
        },
        readonly: true,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-chart-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'chart.xlsx',
          path: 'chart.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('chart.xlsx'))

    expect(await screen.findByTestId('home-chat-doc-html-preview')).toHaveTextContent(
      '.agent/preview_cache/xlsx-parser-html/chart-cache/index.html',
    )
    expect(screen.queryByTestId('home-chat-univer-sheet-editor')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save chart.xlsx' })).not.toBeInTheDocument()
  })

  it('closes a dirty xlsx preview without showing a discard confirmation', async () => {
    const user = userEvent.setup()
    const sourceBlob = await createXlsxBase64Workbook()
    const confirmMock = vi.fn<(message?: string) => boolean>(() => false)
    vi.stubGlobal('confirm', confirmMock)
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-session',
        file_path: 'budget.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-1',
        source_blob: sourceBlob,
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        warnings: [],
        capabilities: {
          detected_unsupported_features: [],
        },
        readonly: false,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-close-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'budget.xlsx',
          path: 'budget.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('budget.xlsx'))
    await screen.findByTestId('home-chat-univer-sheet-editor')
    expect(screen.queryByRole('button', { name: 'Save budget.xlsx' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close preview' }))

    expect(confirmMock).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.queryByTestId('home-chat-office-sheet-rail')).not.toBeInTheDocument()
    })
  })

  it('does not show save confirmation controls for xlsx sheets with unsupported features', async () => {
    const user = userEvent.setup()
    const sourceBlob = await createXlsxBase64Workbook()
    const confirmMock = vi.fn<(message?: string) => boolean>(() => false)
    vi.stubGlobal('confirm', confirmMock)
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-sheet-session',
        file_path: 'budget.xlsx',
        file_kind: 'sheet',
        engine: 'univer',
        unit_id: 'unit-sheet-1',
        source_blob: sourceBlob,
        source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        warnings: ['Pivot tables are read-only in this preview.'],
        capabilities: {
          detected_unsupported_features: ['pivotTables', 'externalLinks'],
        },
        readonly: false,
      },
    })
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-xlsx-unsupported-save-preview',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'budget.xlsx',
          path: 'budget.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('budget.xlsx'))
    await screen.findByTestId('home-chat-univer-sheet-editor')

    expect(screen.queryByRole('button', { name: 'Save budget.xlsx' })).not.toBeInTheDocument()
    expect(confirmMock).not.toHaveBeenCalled()
    expect(saveWorkspaceOfficeSessionMock).not.toHaveBeenCalled()
  })

  it('downloads workspace files from the latest version in the files list', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileVersionBlobMock.mockResolvedValue(new Blob(['html-latest'], { type: 'text/html' }))
    const clickMock = vi.fn()
    const createdLinks: HTMLAnchorElement[] = []
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const element = originalCreateElement(tagName)
      if (tagName.toLowerCase() === 'a') {
        Object.defineProperty(element, 'click', {
          configurable: true,
          value: clickMock,
        })
        createdLinks.push(element as HTMLAnchorElement)
      }
      return element
    }) as typeof document.createElement)

    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-html-download',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'landing.html',
          file_id: 'file-html-1',
          path: 'work/landing.html',
          type: 'web',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
          current_version_id: 'v0002',
          versions: [
            {
              version_id: 'v0001',
              label: 'Version 1',
              size: 10,
              sha256: 'sha-v1',
              created_at: '2026-04-17T09:00:00Z',
              created_by: 'agent',
            },
            {
              version_id: 'v0002',
              label: 'Version 2',
              size: 12,
              sha256: 'sha-v2',
              created_at: '2026-04-17T09:05:00Z',
              created_by: 'agent',
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.hover(await screen.findByText('landing.html'))
    await user.click(await screen.findByRole('button', { name: 'Download landing.html' }))

    await waitFor(() => {
      expect(fetchWorkspaceFileVersionBlobMock).toHaveBeenCalledWith('42', 'file-html-1', 'v0002')
    })
    expect(fetchWorkspaceHtmlBundleBlobMock).not.toHaveBeenCalled()
    expect(clickMock).toHaveBeenCalled()
    expect(createdLinks[createdLinks.length - 1]?.download).toBe('landing.html')
  })

  it('downloads the selected preview version instead of the latest workspace version', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileVersionBlobMock.mockResolvedValue(new Blob(['# selected version'], { type: 'text/markdown' }))
    const clickMock = vi.fn()
    const createdLinks: HTMLAnchorElement[] = []
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const element = originalCreateElement(tagName)
      if (tagName.toLowerCase() === 'a') {
        Object.defineProperty(element, 'click', {
          configurable: true,
          value: clickMock,
        })
        createdLinks.push(element as HTMLAnchorElement)
      }
      return element
    }) as typeof document.createElement)

    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-html-preview-download',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'notes.md',
          file_id: 'file-markdown-1',
          path: 'work/notes.md',
          type: 'text',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
          current_version_id: 'v0002',
          versions: [
            {
              version_id: 'v0001',
              label: 'Version 1',
              size: 10,
              sha256: 'sha-v1',
              created_at: '2026-04-17T09:00:00Z',
              created_by: 'agent',
            },
            {
              version_id: 'v0002',
              label: 'Version 2',
              size: 12,
              sha256: 'sha-v2',
              created_at: '2026-04-17T09:05:00Z',
              created_by: 'agent',
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('notes.md'))
    await screen.findByTestId('home-chat-markdown-preview')

    await user.click(screen.getByRole('button', { name: 'homeHarness.fileVersions.previous' }))
    await user.click(screen.getByRole('button', { name: 'Localized Download' }))

    await waitFor(() => {
      expect(fetchWorkspaceFileVersionBlobMock).toHaveBeenCalledWith('42', 'file-markdown-1', 'v0001')
    })
    expect(fetchWorkspaceHtmlBundleBlobMock).not.toHaveBeenCalled()
    expect(clickMock).toHaveBeenCalled()
    expect(createdLinks[createdLinks.length - 1]?.download).toBe('notes.md')
  })

  it('renders pending homepage attachments as compact preview cards with remove buttons', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Attachment Sources' }))
    const input = screen.getByTestId('home-chat-local-upload-input') as HTMLInputElement
    await user.upload(input, new File(['demo'], 'demo.png', { type: 'image/png' }))

    await waitFor(() => {
      expect(uploadAttachmentMock).toHaveBeenCalled()
    })

    const previewImage = await screen.findByAltText('demo.png')
    expect(previewImage).toBeInTheDocument()
    await waitFor(() => {
      expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith(
        '42',
        'references/inputs/upload_abc123/source.png',
        'preview-token',
        { width: 256 },
      )
    })
    expect(fetchWorkspaceFileBlobMock).not.toHaveBeenCalledWith('42', 'references/inputs/upload_abc123/source.png')
    expect(previewImage.getAttribute('src')).toContain('/preview-files/references%2Finputs%2Fupload_abc123%2Fsource.png')
    expect(previewImage.getAttribute('src')).toContain('w=256')

    expect(screen.getByRole('button', { name: 'Remove attachment 1' })).toBeInTheDocument()
  })

  it('hydrates homepage draft, attachments, and mode from a one-time canvas transfer', async () => {
    const transferKey = 'home-forward-transfer:test-key'
    localStorage.setItem(transferKey, JSON.stringify({
      key: transferKey,
      createdAt: '2026-04-23T00:00:00.000Z',
      source: 'canvas-agent',
      projectId: 7,
      mode: 'document',
      text: 'Bring this over from canvas',
      attachments: [
        {
          id: 99,
          url: 'https://example.com/from-canvas.png',
          type: 'image',
          origin_kind: 'local_upload',
          source_asset_id: null,
        },
      ],
    }))
    window.history.replaceState({}, '', `/dashboard/home?forwardTransferKey=${encodeURIComponent(transferKey)}`)

    render(<ChatHomePage />)

    expect(await screen.findByDisplayValue('Bring this over from canvas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove attachment 1' })).toBeInTheDocument()
    expect(storeState.activateSkill).toHaveBeenCalledWith(null)
    expect(storeState.sendMessage).not.toHaveBeenCalled()
    expect(localStorage.getItem(transferKey)).toBeNull()
    expect(window.location.search).not.toContain('forwardTransferKey')
  })

  it('treats pasted clipboard images as local uploads on the homepage composer', async () => {
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    render(<ChatHomePage />)

    const pastedImage = new File(['paste-image'], 'clipboard.png', { type: 'image/png' })
    const composer = screen.getByTestId('home-chat-composer-input')
    fireEvent.paste(composer, {
      clipboardData: {
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => pastedImage,
          },
        ],
      },
    })

    await waitFor(() => {
      expect(uploadAttachmentMock).toHaveBeenCalled()
    })

    const previewImage = await screen.findByAltText('demo.png')
    expect(previewImage).toBeInTheDocument()
    await waitFor(() => {
      expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith(
        '42',
        'references/inputs/upload_abc123/source.png',
        'preview-token',
        { width: 256 },
      )
    })
    expect(previewImage.getAttribute('src')).toContain('w=256')
  })

  it('supports drag and drop uploads on the homepage composer', async () => {
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    render(<ChatHomePage />)

    const droppedImage = new File(['drop-image'], 'dropped.png', { type: 'image/png' })
    const dropZone = screen.getByTestId('home-chat-composer-dropzone')
    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [droppedImage],
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => droppedImage,
          },
        ],
      },
    })

    await waitFor(() => {
      expect(uploadAttachmentMock).toHaveBeenCalled()
    })

    const previewImage = await screen.findByAltText('demo.png')
    expect(previewImage).toBeInTheDocument()
    await waitFor(() => {
      expect(getWorkspacePreviewFileUrlMock).toHaveBeenCalledWith(
        '42',
        'references/inputs/upload_abc123/source.png',
        'preview-token',
        { width: 256 },
      )
    })
    expect(previewImage.getAttribute('src')).toContain('w=256')
  })

  it('renders sent user message image and file attachments above the message text', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: 'Please use this reference',
          attachments: [
            {
              type: 'image',
              url: 'https://example.com/reference.png',
              name: 'reference.png',
            },
            {
              type: 'file',
              url: 'https://example.com/brief.pdf',
              name: 'brief.pdf',
            },
          ],
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    const messageImage = screen.getByAltText('reference.png')
    expect(messageImage).toBeInTheDocument()
    expect(messageImage.getAttribute('src')).toBe('https://example.com/reference.png')
    expect(screen.getByText('brief.pdf')).toBeInTheDocument()
    expect(screen.getByText('Please use this reference')).toBeInTheDocument()
  })

  it('opens image attachments from the main conversation in a fullscreen preview', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      messages: [
        {
          id: 'user-attachment-preview',
          role: 'user',
          content: 'Reference image',
          attachments: [
            {
              type: 'image',
              url: 'https://example.com/reference-preview.png',
              name: 'reference-preview.png',
            },
          ],
          createdAt: '2026-04-17T10:09:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByAltText('reference-preview.png'))

    expect(await screen.findAllByAltText('reference-preview.png')).toHaveLength(2)
  })

  it('keeps assistant generation cards visible alongside homepage attachments', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      messages: [
        {
          id: 'user-3',
          role: 'user',
          content: 'Send this',
          attachments: [
            {
              type: 'file',
              url: 'https://example.com/source.txt',
              name: 'source.txt',
            },
          ],
          createdAt: '2026-04-17T10:10:00Z',
        },
        {
          id: 'assistant-3',
          role: 'assistant',
          content: 'Done',
          blocks: [
            {
              id: 'generation-1',
              kind: 'tool',
              uiKind: 'generation_card',
              payload: {
                taskId: 7,
                status: 'completed',
                resultUrl: 'https://example.com/generated.png',
                prompt: 'Poster concept',
                modelLabel: 'Image Pro',
              },
            },
          ],
          createdAt: '2026-04-17T10:11:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText('source.txt')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Toggle generation 7' }))
    expect(await screen.findByAltText('Poster concept')).toBeInTheDocument()
  })

  it('resolves harness workspace attachment paths to downloadable image URLs', async () => {
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    Object.assign(storeState, {
      conversationId: '1776420349887_af4d5d',
      messages: [
        {
          id: 'user-2',
          role: 'user',
          content: 'Analyze this image',
          attachments: [
            {
              type: 'image',
              url: 'references/inputs/upload_abc123/source.png',
              name: 'upload.png',
            },
          ],
          createdAt: '2026-04-17T10:05:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('1776420349887_af4d5d', 'references/inputs/upload_abc123/source.png')
    })
    expect(screen.getByAltText('upload.png').getAttribute('src')).toBe('blob:workspace-media')
  })

  it('renders assistant text output as markdown instead of plain text', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-markdown-1',
          role: 'assistant',
          content: '# Summary\n\n- **bold** item',
          createdAt: '2026-04-17T10:20:00Z',
        },
      ],
    })

    const { container } = render(<ChatHomePage />)

    const heading = screen.getByRole('heading', { name: 'Summary' })
    expect(heading).toBeInTheDocument()
    expect(container.querySelector('strong')?.textContent).toBe('bold')
  })

  it('renders subagent summaries as markdown', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-subagent-markdown-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'subagent-card-1',
              kind: 'tool',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'subagent_card',
              expanded: true,
              label: 'Photo search',
              summary: '## Results\n\n| File | Size |\n| --- | --- |\n| `kant_portrait.jpg` | **7.3 MB** |',
              payload: {
                status: 'completed',
                purpose: 'Search philosopher portraits',
              },
            },
          ],
          createdAt: '2026-04-17T10:25:00Z',
        },
      ],
    })

    const { container } = render(<ChatHomePage />)

    expect(screen.getByRole('heading', { name: 'Results' })).toBeInTheDocument()
    expect(container.querySelector('table')).toBeInTheDocument()
    expect(container.querySelector('strong')?.textContent).toBe('7.3 MB')
  })

  it('hides raw streaming tool text output on the homepage while the response is in flight', () => {
    Object.assign(storeState, {
      isStreaming: true,
      streamingBlocks: [
        {
          id: 'stream-tool-1',
          kind: 'tool',
          order: 0,
          status: 'running',
          visible: true,
          uiKind: 'stream_panel',
          payload: {
            toolName: 'lc_read_file',
            streamText: '## Reading file\n\nLoaded `README.md`',
          },
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByRole('heading', { name: 'Reading file' })).not.toBeInTheDocument()
    expect(screen.queryByText('README.md')).not.toBeInTheDocument()
  })

  it('does not show the thinking placeholder when a running generation card is already visible', () => {
    Object.assign(storeState, {
      isStreaming: true,
      streamingBlocks: [],
      messages: [
        {
          id: 'assistant-running-generation-visible',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'generation-running-visible',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_video',
                taskId: 201,
                status: 'processing',
                modelLabel: 'Seedance 1.5 Pro',
                duration: '5',
                resolution: '480p',
              },
            },
          ],
          createdAt: '2026-04-18T10:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText(/Generate Video/)).toBeInTheDocument()
    expect(screen.queryByText('Thinking...')).not.toBeInTheDocument()
  })

  it('hides compact tool decision cards on the homepage before results arrive', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-tool-decision-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'tool-decision-1',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'compact_tool',
              payload: {
                toolName: 'file_read',
                callId: 'call-read-1',
                args: {
                  file_path: 'README.md',
                },
                status: 'running',
              },
            },
          ],
          createdAt: '2026-04-17T10:25:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByText(/Read File/i)).not.toBeInTheDocument()
    expect(screen.queryByText('README.md')).not.toBeInTheDocument()
  })

  it('renders completed generation task history blocks with inline media and metadata', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-generation-history-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'generation-history-image',
              kind: 'tool',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_image',
                taskId: 71,
                status: 'completed',
                mediaType: 'image',
                resultUrl: 'https://example.com/generated-coffee.png',
                prompt: 'Coffee poster',
                modelName: 'gemini-3.1-flash-image-preview-official',
                modelLabel: 'Nano Banana 2',
                resolution: '4K',
                result: {
                  taskId: 71,
                  status: 'completed',
                  mediaType: 'image',
                  resultUrl: 'https://example.com/generated-coffee.png',
                  modelName: 'gemini-3.1-flash-image-preview-official',
                  modelLabel: 'Nano Banana 2',
                  resolution: '4K',
                },
              },
            },
            {
              id: 'generation-history-video',
              kind: 'tool',
              order: 1,
              status: 'completed',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_video',
                taskId: 72,
                status: 'completed',
                mediaType: 'video',
                resultUrl: 'https://example.com/generated-coffee.mp4',
                prompt: 'Coffee video',
                modelName: 'kling-v2-6',
                quality: '1080p',
                result: {
                  taskId: 72,
                  status: 'completed',
                  mediaType: 'video',
                  resultUrl: 'https://example.com/generated-coffee.mp4',
                  modelName: 'kling-v2-6',
                  quality: '1080p',
                },
              },
            },
          ],
          createdAt: '2026-04-17T10:26:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Toggle generation 71' }))
    await user.click(screen.getByRole('button', { name: 'Toggle generation 72' }))

    const image = screen.getByAltText('Coffee poster') as HTMLImageElement
    expect(image).toBeInTheDocument()
    expect(image.getAttribute('src')).toBe('https://example.com/generated-coffee.png')
    expect(screen.getByText('Nano Banana 2')).toBeInTheDocument()
    expect(screen.getByText('4K')).toBeInTheDocument()

    const videoPreview = screen.getAllByTestId('canvas-video-item')[0]
    const video = videoPreview.querySelector('video') as HTMLVideoElement | null
    expect(videoPreview).toBeInTheDocument()
    expect(video?.getAttribute('src')).toBe('https://example.com/generated-coffee.mp4')
    expect(screen.getByText('Kling 2.6')).toBeInTheDocument()
    expect(screen.getByText('1080p')).toBeInTheDocument()
  })

  it('keeps generation cards collapsed by default and expands media after clicking the card', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-generation-collapsed-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'generation-collapsed-image',
              kind: 'tool',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_image',
                taskId: 73,
                status: 'completed',
                mediaType: 'image',
                resultUrl: 'https://example.com/collapsed-coffee.png',
                prompt: 'Coffee detail',
                modelLabel: 'NanoBanana2',
                resolution: '4K',
                result: {
                  taskId: 73,
                  status: 'completed',
                  mediaType: 'image',
                  resultUrl: 'https://example.com/collapsed-coffee.png',
                  prompt: 'Coffee detail',
                  modelLabel: 'NanoBanana2',
                  resolution: '4K',
                },
              },
            },
          ],
          createdAt: '2026-04-17T10:27:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByAltText('Coffee detail')).not.toBeInTheDocument()
    expect(screen.getByText('生成图片 / Generate Image')).toBeInTheDocument()
    expect(screen.getByText('NanoBanana2')).toBeInTheDocument()
    expect(screen.getByText('4K')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Toggle generation 73' }))

    expect(await screen.findByAltText('Coffee detail')).toBeInTheDocument()
  })

  it('renders generate_video history blocks as video cards even when mediaType is missing', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-generate-video-history-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'generation-video-history',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_video',
                callId: 'functions.generate_video:0',
                status: 'running',
                modelLabel: 'Kling 2.6',
                args: {
                  aspectRatio: '16:9',
                  duration: '10',
                  resolution: '1080p',
                  quality: 'pro',
                },
              },
            },
          ],
          createdAt: '2026-04-17T10:30:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText(/Generate Video/)).toBeInTheDocument()
    expect(screen.queryByText(/Generate Image/)).not.toBeInTheDocument()
    expect(screen.getByText('Kling 2.6')).toBeInTheDocument()
    expect(screen.getByText('pro · 1080p · 10s · 16:9')).toBeInTheDocument()
  })

  it('renders generation tasks nested inside subagent cards during agent loops', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-subagent-render-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'subagent-card-1',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'subagent_card',
              taskId: 'subagent-1',
              label: 'Coffee loop',
              payload: {
                taskId: 'subagent-1',
                label: 'Coffee loop',
              },
              children: [
                {
                  id: 'subagent-generation-1',
                  kind: 'tool',
                  order: 0,
                  status: 'running',
                  visible: true,
                  uiKind: 'generation_task',
                  payload: {
                    toolName: 'generate_image',
                    taskId: 74,
                    status: 'processing',
                    mediaType: 'image',
                    modelLabel: 'NanoBanana2',
                    resolution: '4K',
                  },
                },
              ],
            },
          ],
          createdAt: '2026-04-17T10:28:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText('Coffee loop')).toBeInTheDocument()
    expect(screen.queryByText('生成图片 / Generate Image')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Coffee loop/ }))

    expect(screen.getByText('生成图片 / Generate Image')).toBeInTheDocument()
  })

  it('renders subagent cards in chronological order and shows purpose and status metadata', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-subagent-order-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'assistant-text-1',
              kind: 'content',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'assistant_text',
              payload: {
                text: '先开始视觉 QA。',
              },
            },
            {
              id: 'subagent-card-order-1',
              kind: 'tool',
              order: 1,
              status: 'completed',
              visible: true,
              uiKind: 'subagent_card',
              taskId: 'subagent-order-1',
              label: 'Visual QA Slides 1-5',
              summary: '检查完成',
              payload: {
                taskId: 'subagent-order-1',
                label: 'Visual QA Slides 1-5',
                purpose: 'Visual QA Slides 1-5',
                status: 'completed',
              },
              children: [
                {
                  id: 'subagent-analysis-1',
                  kind: 'content',
                  order: 0,
                  status: 'completed',
                  visible: true,
                  uiKind: 'media_card',
                  payload: {
                    mediaType: 'image_analysis',
                    text: 'Slide 1 looks good',
                  },
                },
              ],
            },
          ],
          createdAt: '2026-04-17T10:29:00Z',
        },
      ],
    })

    const { container } = render(<ChatHomePage />)

    const intro = screen.getByText('先开始视觉 QA。')
    const purpose = screen.getByText('Visual QA Slides 1-5')
    expect(intro.compareDocumentPosition(purpose) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    expect(screen.getByText('子代理')).toBeInTheDocument()
    expect(screen.getByText('任务目的')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.queryByText('Slide 1 looks good')).not.toBeInTheDocument()
    expect(container.querySelector('button[aria-expanded]')).not.toBeNull()
  })

  it('renders blocked subagent status with the localized label', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-subagent-blocked-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'subagent-card-blocked-1',
              kind: 'tool',
              order: 0,
              status: 'blocked',
              visible: true,
              uiKind: 'subagent_card',
              taskId: 'subagent-blocked-1',
              label: 'Visual QA of 8 slides',
              summary: 'Path resolution blocked the remaining analysis.',
              payload: {
                taskId: 'subagent-blocked-1',
                label: 'Visual QA of 8 slides',
                purpose: 'Visual QA of 8 slides',
                status: 'blocked',
              },
              children: [],
            },
          ],
          createdAt: '2026-04-21T00:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText('子代理')).toBeInTheDocument()
    expect(screen.getByText('任务目的')).toBeInTheDocument()
    expect(screen.getByText('Visual QA of 8 slides')).toBeInTheDocument()
    expect(screen.getByText('已阻塞')).toBeInTheDocument()
  })

  it('shows only current workspace files in the session files modal instead of duplicating generated blocks', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-generated-file-1',
          role: 'assistant',
          content: null,
          blocks: [
            {
              id: 'generation-file-image',
              kind: 'tool',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_image',
                taskId: 75,
                status: 'completed',
                mediaType: 'image',
                resultUrl: 'https://example.com/session-coffee.png',
                prompt: 'Session coffee',
                result: {
                  taskId: 75,
                  status: 'completed',
                  mediaType: 'image',
                  resultUrl: 'https://example.com/session-coffee.png',
                  prompt: 'Session coffee',
                },
              },
            },
            {
              id: 'generation-file-video',
              kind: 'tool',
              order: 1,
              status: 'completed',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                toolName: 'generate_video',
                taskId: 76,
                status: 'completed',
                mediaType: 'video',
                resultUrl: 'https://example.com/session-coffee.mp4',
                prompt: 'Session coffee video',
                result: {
                  taskId: 76,
                  status: 'completed',
                  mediaType: 'video',
                  resultUrl: 'https://example.com/session-coffee.mp4',
                  prompt: 'Session coffee video',
                },
              },
            },
          ],
          createdAt: '2026-04-17T10:29:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'session-coffee.mp4',
          path: 'generated/session-coffee.mp4',
          type: 'video',
          size: 4096,
          created_at: '2026-04-17T10:29:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))

    expect(await screen.findByText('session-coffee.mp4')).toBeInTheDocument()
    expect(screen.queryByText('session-coffee.png')).not.toBeInTheDocument()
  })

  it('resolves locally stored generated media to workspace preview URLs in the session files modal', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['video'], { type: 'video/mp4' }))
    Object.assign(storeState, {
      conversationId: 'conv-local-media',
      messages: [
        {
          id: 'assistant-generated-local-1',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:29:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'session-coffee.mp4',
          path: 'generated/session-coffee.mp4',
          type: 'video',
          size: 4096,
          created_at: '2026-04-17T10:29:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))
    await user.click(await screen.findByText('session-coffee.mp4'))

    expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('conv-local-media', 'generated/session-coffee.mp4')
    expect((await screen.findByTestId('home-chat-video-preview')).getAttribute('src')).toBe(
      'blob:workspace-media',
    )
  })

  it('resolves generated media sizes from current workspace files instead of showing 0 B', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      headers: {
        get: () => '4096',
      },
    }))

    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-generated-size-1',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:31:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'generated-size.png',
          path: 'https://example.com/generated-size.png',
          type: 'image',
          size: 0,
          created_at: '2026-04-17T10:31:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Files (1)' }))

    expect(await screen.findByText('generated-size.png')).toBeInTheDocument()
    expect(await screen.findByText('4.0 KB')).toBeInTheDocument()
  })

  it('keeps homepage history and message panes in fixed internal scroll containers', () => {
    const { container } = render(<ChatHomePage />)

    const historyPane = container.querySelector('[data-testid="home-chat-history-scroll"]')
    const messagePane = container.querySelector('[data-testid="home-chat-message-scroll"]')

    expect(historyPane?.className).toContain('overflow-y-auto')
    expect(messagePane?.className).toContain('overflow-y-auto')
    expect(messagePane?.className).toContain('min-h-0')
  })

  it('shows a stop control when the harness run is active even without visible streaming tokens', async () => {
    Object.assign(storeState, {
      runStatus: 'running',
      isStreaming: false,
    })

    render(<ChatHomePage />)

    fireEvent.click(screen.getByRole('button', { name: /stop agent response/i }))

    expect(storeState.stopStreaming).toHaveBeenCalledTimes(1)
  })
})



