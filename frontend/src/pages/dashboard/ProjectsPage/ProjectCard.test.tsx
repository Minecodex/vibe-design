import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import type { ProjectListItemRead } from '@/api/endpoints/projects'
import { ProjectCard } from './ProjectCard'

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (_key: string, options?: { count?: number; date?: string }) => {
      if (typeof options?.count === 'number') {
        return String(options.count)
      }
      return options?.date ?? _key
    },
  }),
}))

vi.mock('./useProjectCardVisibility', () => ({
  useProjectCardVisibility: () => ({
    isActive: true,
    ref: { current: null },
  }),
}))

const project: ProjectListItemRead = {
  id: 1,
  user_id: 1,
  title: 'Preview Project',
  thumbnail_url: null,
  project_preview_items: [
    {
      asset_type: 'image',
      url: 'https://example.com/original.png',
      list_preview_url: 'https://example.com/original__list_320.webp?v=1',
      list_preview_status: 'ready',
    },
  ],
  status: 'pending',
  share_token: null,
  share_permission: null,
  share_password: null,
  share_expiration: null,
  created_at: '2026-03-18T12:00:00',
  updated_at: '2026-03-18T12:00:00',
  users: [],
}

describe('ProjectCard', () => {
  test('prefers project preview thumbnails for image mosaics', () => {
    const { container } = render(
      <ProjectCard
        currentUser={{ id: 1, username: 'owner', role: 'user' }}
        formatDate={() => '2026-03-18'}
        onDelete={vi.fn()}
        onOpenDetails={vi.fn()}
        onOpenMembers={vi.fn()}
        onOpenShare={vi.fn()}
        onProjectClick={vi.fn()}
        ownerOnlyHint="owner-only"
        project={project}
      />,
    )

    expect(screen.getByText('Preview Project')).toBeInTheDocument()
    expect(container.querySelector('img[src*="original__list_320.webp"]')).toBeInTheDocument()
    expect(container.querySelector('img[src="https://example.com/original.png"]')).not.toBeInTheDocument()
  })
})
