import { render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ShareModal } from './ShareModal'
import type { ProjectRead } from '@/api/endpoints/projects'

const generateLinkMock = vi.fn()
const writeTextMock = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/api/endpoints/share', () => ({
  shareApi: {
    generateLink: (...args: unknown[]) => generateLinkMock(...args),
  },
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ShareModal', () => {
  beforeEach(() => {
    generateLinkMock.mockReset()
    writeTextMock.mockReset()
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: writeTextMock,
      },
    })
  })

  it('preserves existing canvas data when share updates return a partial project payload', async () => {
    const user = userEvent.setup()
    const onUpdate = vi.fn()
    const project: ProjectRead = {
      id: 1,
      user_id: 9,
      title: 'Project Alpha',
      thumbnail_url: null,
      canvas_data: [
        {
          id: 'image-1',
          type: 'image',
          url: 'https://example.com/cover.png',
          x: 0,
          y: 0,
        },
      ],
      status: 'pending',
      share_token: null,
      share_permission: null,
      share_password: null,
      share_expiration: null,
      created_at: '2026-03-18T12:00:00Z',
      updated_at: '2026-03-18T12:00:00Z',
      users: [
        {
          id: 9,
          nickname: 'Owner',
          username: 'owner',
          avatar_url: null,
          role: 'owner',
        },
      ],
    }

    generateLinkMock.mockResolvedValue({
      data: {
        ...project,
        canvas_data: null,
        users: undefined,
        share_token: 'viewer-token',
        share_permission: 'editor',
        share_expiration: 1_800_000_000,
      },
    })
    writeTextMock.mockResolvedValue(undefined)

    render(
      <ShareModal
        open
        onClose={() => {}}
        project={project}
        onUpdate={onUpdate}
      />
    )

    const shareButtons = document.body.querySelectorAll('button[data-variant="outline"]')
    expect(shareButtons).toHaveLength(2)

    await user.click(shareButtons[0] as HTMLButtonElement)

    await waitFor(() => {
      expect(generateLinkMock).toHaveBeenCalledWith(1, 'editor')
    })

    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 1,
          share_token: 'viewer-token',
          share_permission: 'editor',
          canvas_data: project.canvas_data,
          users: project.users,
        })
      )
    })

  })
})
