import type { CanvasItem, ProjectRead } from '@/api/endpoints/projects'

export function canvasItem(overrides: Partial<CanvasItem>): CanvasItem {
  return { id: 'fixture-item', type: 'image', url: '/fixture.png', x: 0, y: 0, ...overrides }
}

export function projectRead(overrides: Partial<ProjectRead>): ProjectRead {
  return { id: 7, user_id: 1, title: 'Fixture project', thumbnail_url: null, status: 'active',
    share_token: null, share_permission: null, share_password: null, share_expiration: null,
    created_at: '2026-05-01T00:00:00Z', updated_at: '2026-05-01T00:00:00Z', ...overrides }
}
