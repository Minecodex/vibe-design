import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { HomeChatFileVersionControl } from './HomeChatFileVersionControl'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (key === 'homeHarness.fileVersions.versionCounter') {
        return `Version ${values?.current}/${values?.total}`
      }
      if (key === 'homeHarness.fileVersions.previous') {
        return 'Previous version'
      }
      if (key === 'homeHarness.fileVersions.next') {
        return 'Next version'
      }
      if (key === 'homeHarness.fileVersions.versionLabel') {
        return `Version ${values?.number}`
      }
      return key
    },
  }),
}))

describe('HomeChatFileVersionControl', () => {
  it('renders as a header action with a dropdown below the trigger', async () => {
    const user = userEvent.setup()
    const onSelectVersion = vi.fn()

    render(
      <HomeChatFileVersionControl
        file={{
          name: 'report.xlsx',
          path: 'report.xlsx',
          type: 'table',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
          current_version_id: 'v2',
          versions: [
            {
              version_id: 'v1',
              label: 'Version 1',
              size: 10,
              sha256: 'sha-v1',
              created_at: '2026-04-17T09:00:00Z',
              created_by: 'agent',
            },
            {
              version_id: 'v2',
              label: 'Version 2',
              size: 12,
              sha256: 'sha-v2',
              created_at: '2026-04-17T09:05:00Z',
              created_by: 'agent',
            },
          ],
        }}
        selectedVersionId={null}
        isDark={false}
        onSelectVersion={onSelectVersion}
      />,
    )

    const root = screen.getByTestId('home-chat-file-version-control')
    expect(root).not.toHaveClass('absolute')
    expect(root).not.toHaveClass('bottom-4')
    expect(screen.getByTestId('home-chat-file-version-menu')).toHaveClass('top-full')
    expect(screen.getByTestId('home-chat-file-version-menu')).toHaveClass('pt-2')

    await user.click(screen.getByRole('button', { name: 'Previous version' }))
    expect(onSelectVersion).toHaveBeenCalledWith('v1')
  })
})
