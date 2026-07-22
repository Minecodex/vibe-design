import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { ProjectFolderGrid } from './ProjectFolderGrid'

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

describe('ProjectFolderGrid', () => {
  test('renders aggregated project summaries and opens the selected folder', async () => {
    const user = userEvent.setup()
    const onFolderClick = vi.fn()

    render(
      <ProjectFolderGrid
        projects={[
          {
            project_id: 9,
            project_name: 'Motion System',
            asset_count: 3,
            image_count: 2,
            video_count: 1,
            latest_asset_updated_at: '2026-04-01T03:00:00',
          },
        ]}
        onFolderClick={onFolderClick}
      />,
    )

    expect(screen.getByText('Motion System')).toBeInTheDocument()
    expect(screen.getByText('3 items')).toBeInTheDocument()

    await user.click(screen.getByText('Motion System'))

    expect(onFolderClick).toHaveBeenCalledWith(9, 'Motion System')
  })
})
