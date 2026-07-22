import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AttachmentCardStrip } from './AttachmentCardStrip'

const getWorkspaceFileUrlMock = vi.fn()
const fetchWorkspaceFileBlobMock = vi.fn()
const getApiOriginMock = vi.fn()

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getWorkspaceFileUrl: (...args: unknown[]) => getWorkspaceFileUrlMock(...args),
    fetchWorkspaceFileBlob: (...args: unknown[]) => fetchWorkspaceFileBlobMock(...args),
  },
}))

vi.mock('@/config/runtimeConfig', () => ({
  getApiOrigin: () => getApiOriginMock(),
}))

describe('AttachmentCardStrip', () => {
  beforeEach(() => {
    getWorkspaceFileUrlMock.mockReset()
    fetchWorkspaceFileBlobMock.mockReset()
    getApiOriginMock.mockReset()

    getWorkspaceFileUrlMock.mockReturnValue(
      '/api/v1/agent/harness/conversations/conv-1/files/references/inputs/upload_001/source.png',
    )
    getApiOriginMock.mockReturnValue('http://localhost:8000')

    URL.createObjectURL = vi.fn()
    URL.revokeObjectURL = vi.fn()
  })

  it('loads protected harness image attachments through an authenticated blob request', async () => {
    vi.mocked(URL.createObjectURL).mockReturnValue('blob:attachment-inline')
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image-bytes'], { type: 'image/png' }))

    render(
      <AttachmentCardStrip
        attachments={[
          {
              type: 'image',
              url: 'references/inputs/upload_001/source.png',
              name: 'upload.png',
          },
        ]}
        isDark={false}
        conversationId="conv-1"
      />,
    )

    await waitFor(() => {
      expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledWith('conv-1', 'references/inputs/upload_001/source.png')
    })

    expect(screen.getByAltText('upload.png')).toHaveAttribute('src', 'blob:attachment-inline')
  })

  it('uses a dedicated blob URL when opening protected attachment previews', async () => {
    const user = userEvent.setup()
    vi.mocked(URL.createObjectURL)
      .mockReturnValueOnce('blob:attachment-inline')
      .mockReturnValueOnce('blob:attachment-dialog')
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['image-bytes'], { type: 'image/png' }))

    render(
      <AttachmentCardStrip
        attachments={[
          {
              type: 'image',
              url: 'references/inputs/upload_001/source.png',
              name: 'upload.png',
          },
        ]}
        isDark={false}
        conversationId="conv-1"
      />,
    )

    const image = await screen.findByAltText('upload.png')
    await user.click(image)

    const images = await screen.findAllByAltText('upload.png')
    expect(fetchWorkspaceFileBlobMock).toHaveBeenCalledTimes(2)
    expect(images[0]).toHaveAttribute('src', 'blob:attachment-inline')
    expect(images[1]).toHaveAttribute('src', 'blob:attachment-dialog')
  })

  it('resolves non-workspace relative image paths against the API origin', () => {
    render(
      <AttachmentCardStrip
        attachments={[
          {
            type: 'image',
            url: 'dashboard/files/upload_da0244d33abc.jpg',
            name: 'upload_da0244d33abc.jpg',
          },
        ]}
        isDark={false}
      />,
    )

    expect(screen.getByAltText('upload_da0244d33abc.jpg')).toHaveAttribute(
      'src',
      'http://localhost:8000/dashboard/files/upload_da0244d33abc.jpg',
    )
  })

  it('keeps deferred local data URLs intact for new-conversation previews', () => {
    render(
      <AttachmentCardStrip
        attachments={[
          {
            type: 'image',
            url: 'data:image/png;base64,ZmFrZS1pbWFnZQ==',
            name: 'draft.png',
          },
        ]}
        isDark={false}
      />,
    )

    expect(screen.getByAltText('draft.png')).toHaveAttribute(
      'src',
      'data:image/png;base64,ZmFrZS1pbWFnZQ==',
    )
  })

  it('renders docx and xlsx attachments as compact icon cards', () => {
    render(
      <AttachmentCardStrip
        attachments={[
          {
            type: 'file',
            url: 'references/inputs/upload_001/brief.docx',
            name: 'brief.docx',
          },
          {
            type: 'file',
            url: 'references/inputs/upload_002/budget.xlsx',
            name: 'budget.xlsx',
          },
        ]}
        isDark={false}
        conversationId="conv-1"
      />,
    )

    expect(screen.getByText('brief.docx')).toBeInTheDocument()
    expect(screen.getByText('budget.xlsx')).toBeInTheDocument()
    expect(screen.getByTestId('attachment-kind-document')).toBeInTheDocument()
    expect(screen.getByTestId('attachment-kind-spreadsheet')).toBeInTheDocument()
  })

  it('opens workspace text attachments through the right rail callback', async () => {
    const user = userEvent.setup()
    const onOpenWorkspaceRelativeFile = vi.fn()

    render(
      <AttachmentCardStrip
        attachments={[
          {
            type: 'file',
            url: 'references/inputs/upload_001/account.txt',
            name: 'account.txt',
          },
        ]}
        isDark={false}
        conversationId="conv-1"
        onOpenWorkspaceRelativeFile={onOpenWorkspaceRelativeFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: /account\.txt/i }))

    expect(onOpenWorkspaceRelativeFile).toHaveBeenCalledWith(
      'references/inputs/upload_001/account.txt',
      'account.txt',
    )
  })
})
