import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  buildCanvasExportFilenameMap,
  normalizeCanvasExportFilenamePart,
} from './canvasExportFilename'

function makeItem(overrides: Partial<CanvasItem>): CanvasItem {
  return {
    id: 'item',
    type: 'image',
    url: '/image.png',
    x: 0,
    y: 0,
    ...overrides,
  } as CanvasItem
}

describe('buildCanvasExportFilenameMap', () => {
  it('uses project, group, and sequential numbers when exporting a selected group', () => {
    const group = makeItem({ id: 'group-1', type: 'group', name: 'Lookbook' })
    const firstImage = makeItem({ id: 'image-1', name: 'Hero.png', groupId: 'group-1' })
    const secondImage = makeItem({ id: 'image-2', name: 'Detail.png', groupId: 'group-1' })

    const filenames = buildCanvasExportFilenameMap({
      projectName: 'Launch',
      canvasItems: [group, firstImage, secondImage],
      targetItemIds: ['group-1'],
      exportItems: [firstImage, secondImage],
    })

    expect(filenames.get('image-1')).toBe('Launch_Lookbook_01')
    expect(filenames.get('image-2')).toBe('Launch_Lookbook_02')
  })

  it('uses project and image names when multiple image items are selected directly', () => {
    const group = makeItem({ id: 'group-1', type: 'group', name: 'Lookbook' })
    const firstImage = makeItem({ id: 'image-1', name: 'Hero.png', groupId: 'group-1' })
    const secondImage = makeItem({ id: 'image-2', name: 'Detail.jpg', groupId: 'group-1' })

    const filenames = buildCanvasExportFilenameMap({
      projectName: 'Launch',
      canvasItems: [group, firstImage, secondImage],
      targetItemIds: ['image-1', 'image-2'],
      exportItems: [firstImage, secondImage],
    })

    expect(filenames.get('image-1')).toBe('Launch_Hero')
    expect(filenames.get('image-2')).toBe('Launch_Detail')
  })

  it('uses project and image name for a single ungrouped image', () => {
    const image = makeItem({ id: 'image-1', name: 'Cover.webp' })

    const filenames = buildCanvasExportFilenameMap({
      projectName: 'Brand Refresh',
      canvasItems: [image],
      targetItemIds: ['image-1'],
      exportItems: [image],
    })

    expect(filenames.get('image-1')).toBe('Brand Refresh_Cover')
  })

  it('sanitizes names and appends a suffix when exported bases collide', () => {
    const firstImage = makeItem({ id: 'image-1', name: 'Hero/Image.png' })
    const secondImage = makeItem({ id: 'image-2', name: 'Hero?Image.jpg' })

    const filenames = buildCanvasExportFilenameMap({
      projectName: 'Project: One',
      canvasItems: [firstImage, secondImage],
      targetItemIds: ['image-1', 'image-2'],
      exportItems: [firstImage, secondImage],
    })

    expect(filenames.get('image-1')).toBe('Project_ One_Hero_Image')
    expect(filenames.get('image-2')).toBe('Project_ One_Hero_Image_2')
  })

  it('normalizes reserved filename parts', () => {
    expect(normalizeCanvasExportFilenamePart('CON', 'fallback')).toBe('CON_')
  })
})
