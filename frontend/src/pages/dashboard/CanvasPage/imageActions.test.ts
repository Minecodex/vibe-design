import { describe, expect, it } from 'vitest'

import type { AssetRead } from '@/api/endpoints/assets'
import type { CanvasItem } from '@/api/endpoints/projects'

import {
  IMAGE_DETAIL_PANEL_HEIGHT,
  IMAGE_DETAIL_PANEL_WIDTH,
  clampCanvasStackZIndex,
  closeImageDetails,
  formatImageDetails,
  formatImageSizeLabel,
  getNextCanvasStackZIndex,
  getImageDetailPanelPosition,
  getImageDetailAsset,
  getImageExportDimensions,
  getMediaRestoreRect,
  openImageDetails,
  removeCanvasImage,
  shouldShowGeneratorControlPanel,
  shouldShowImageToolbar,
  shouldShowSelectionMeta,
} from './imageActions'

describe('imageActions', () => {
  const baseItem: CanvasItem = {
    id: 'image-1',
    type: 'image',
    url: 'https://example.com/media/photo.final.JPG?token=1',
    x: 120,
    y: 64,
    width: 320,
    height: 180,
    source_asset_id: 99,
    asset_origin: 'local_upload',
  }

  it('removes the target canvas item immediately and returns related asset id', () => {
    const syncedAsset: AssetRead = {
      id: 501,
      project_id: 8,
      user_id: 12,
      asset_type: 'image',
      url: baseItem.url,
      created_at: '2026-03-17 08:00:00',
      updated_at: '2026-03-18 09:30:00',
      adder_avatar: 'https://example.com/synced-avatar.png',
      adder_nickname: 'Synced User',
      is_favorite: false,
      origin_kind: 'legacy',
      canvas_item_id: baseItem.id,
      source_asset_id: 99,
    }

    const result = removeCanvasImage({
      canvasItems: [
        baseItem,
        { ...baseItem, id: 'image-2', source_asset_id: 101 },
      ],
      selectedItems: ['image-1'],
      itemId: 'image-1',
      projectAssets: {
        501: syncedAsset,
      },
    })

    expect(result.canvasItems.map((item) => item.id)).toEqual(['image-2'])
    expect(result.selectedItems).toEqual([])
    expect(result.assetIdsToDelete).toEqual([501])
  })

  it('falls back to source asset id when there is no synced asset matched by canvas item id', () => {
    const result = removeCanvasImage({
      canvasItems: [baseItem],
      selectedItems: ['image-1'],
      itemId: 'image-1',
      projectAssets: {},
    })

    expect(result.assetIdsToDelete).toEqual([99])
  })

  it('opens image details by clearing selection and tracking the active detail item', () => {
    expect(openImageDetails({ itemId: 'image-1', selectedItems: ['image-1'] })).toEqual({
      detailItemId: 'image-1',
      selectedItems: [],
    })
  })

  it('closes image details by restoring selection to the image item', () => {
    expect(closeImageDetails('image-1')).toEqual({
      detailItemId: null,
      selectedItems: ['image-1'],
    })
  })

  it('formats image detail metadata with asset creator information and creation time', () => {
    const asset: AssetRead = {
      id: 99,
      project_id: 8,
      user_id: 3,
      asset_type: 'image',
      url: baseItem.url,
      created_at: '2026-03-18T08:00:00Z',
      updated_at: '2026-03-18T09:30:00Z',
      adder_avatar: 'https://example.com/avatar.png',
      adder_nickname: 'Alice',
      is_favorite: false,
      origin_kind: 'local_upload',
      source_asset_id: null,
    }

    const details = formatImageDetails(baseItem, asset, 1_572_864)

    expect(details.creatorName).toBe('Alice')
    expect(details.creatorAvatar).toBe('https://example.com/avatar.png')
    expect(details.fileFormat).toBe('JPG')
    expect(details.imageSize).toBe('1.50 MB')
    expect(details.updatedAt).toContain('2026')
  })

  it('adds AI generation metadata only for AI-generated images', () => {
    const details = formatImageDetails({
      ...baseItem,
      asset_origin: 'ai_generated',
      source_asset_id: undefined,
      prompt: 'golden hour city street with reflective rain',
      model_label: 'Nano Banana 2',
      created_at: '2026-04-16T08:00:00Z',
      creator_name: 'Canvas Creator',
      creator_avatar: '/uploads/avatars/creator.png',
      resolution: '2K',
      model_name: 'Seedream-5.0-Lite',
    })

    expect(details.creatorName).toBe('Canvas Creator')
    expect(details.creatorAvatar).toBe('/uploads/avatars/creator.png')
    expect(details.updatedAt).toContain('2026')
    expect(details.generationMeta).toEqual({
      model: 'Nano Banana 2',
      resolution: '2K',
      dimensions: '320 x 180 px',
      prompt: 'golden hour city street with reflective rain',
    })
  })

  it('falls back to the current user when asset creator info is unavailable', () => {
    const details = formatImageDetails(
      {
        ...baseItem,
        asset_origin: 'ai_generated',
      },
      null,
      null,
      {
        creatorName: 'Current User',
        creatorAvatar: '/uploads/avatars/current-user.png',
      },
    )

    expect(details.creatorName).toBe('Current User')
    expect(details.creatorAvatar).toBe('/uploads/avatars/current-user.png')
  })

  it('keeps upload image details free of AI-only generation metadata', () => {
    const details = formatImageDetails({
      ...baseItem,
      asset_origin: 'local_upload',
      prompt: 'should not leak into upload details',
      resolution: '2K',
      model_name: 'Seedream-5.0-Lite',
    })

    expect(details.generationMeta).toBeNull()
  })

  it('prefers the synced project asset matched by canvas item id for creator and creation info', () => {
    const syncedAsset: AssetRead = {
      id: 501,
      project_id: 8,
      user_id: 12,
      asset_type: 'image',
      url: baseItem.url,
      created_at: '2026-03-17 08:00:00',
      updated_at: '2026-03-18 09:30:00',
      adder_avatar: 'https://example.com/synced-avatar.png',
      adder_nickname: 'Synced User',
      is_favorite: false,
      origin_kind: 'legacy',
      canvas_item_id: baseItem.id,
      source_asset_id: 99,
    }

    const originalSourceAsset: AssetRead = {
      id: 99,
      project_id: 1,
      user_id: 2,
      asset_type: 'image',
      url: baseItem.url,
      created_at: '2026-03-10 08:00:00',
      updated_at: '2026-03-10 10:00:00',
      adder_avatar: null,
      adder_nickname: 'Original Owner',
      is_favorite: false,
      origin_kind: 'legacy',
      canvas_item_id: null,
      source_asset_id: null,
    }

    const asset = getImageDetailAsset(baseItem, {
      99: originalSourceAsset,
      501: syncedAsset,
    })

    const details = formatImageDetails(baseItem, asset)

    expect(asset?.id).toBe(501)
    expect(details.creatorName).toBe('Synced User')
    expect(details.creatorAvatar).toBe('https://example.com/synced-avatar.png')
    expect(details.updatedAt).not.toBe('--')
    expect(details.updatedAt).toContain('2026')
  })

  it('falls back to updated_at when created_at is missing', () => {
    const details = formatImageDetails(baseItem, {
      id: 77,
      project_id: 8,
      user_id: 3,
      asset_type: 'image',
      url: baseItem.url,
      created_at: '',
      updated_at: '2026-03-18T09:30:00Z',
      adder_avatar: null,
      adder_nickname: 'Alice',
      is_favorite: false,
      origin_kind: 'local_upload',
      source_asset_id: null,
    })

    expect(details.updatedAt).toContain('2026')
  })

  it('calculates a fixed-size detail panel position to the right of the image', () => {
    const position = getImageDetailPanelPosition({
      item: baseItem,
      zoom: 200,
      offset: { x: 40, y: 24 },
      viewport: { width: 1200, height: 900 },
    })

    expect(position.width).toBe(IMAGE_DETAIL_PANEL_WIDTH)
    expect(position.height).toBe(IMAGE_DETAIL_PANEL_HEIGHT)
    expect(position.left).toBe(808)
    expect(position.top).toBe(152)
  })

  it('formats byte sizes into kb or mb labels and shows placeholder when size is unavailable', () => {
    expect(formatImageSizeLabel(baseItem, 2_048)).toBe('2.00 KB')
    expect(formatImageSizeLabel(baseItem, 3_145_728)).toBe('3.00 MB')
    expect(formatImageSizeLabel(baseItem, null)).toBe('--')
  })

  it('hides the top selection meta row when the item is too narrow', () => {
    expect(shouldShowSelectionMeta(420)).toBe(true)
    expect(shouldShowSelectionMeta(280)).toBe(false)
  })

  it('shows the top image toolbar only for real image assets', () => {
    expect(shouldShowImageToolbar('image')).toBe(true)
    expect(shouldShowImageToolbar('image_generator')).toBe(false)
    expect(shouldShowImageToolbar('video')).toBe(false)
    expect(shouldShowImageToolbar('video_generator')).toBe(false)
    expect(shouldShowImageToolbar('group')).toBe(false)
  })

  it('hides the generator control panel when a generator item has failed', () => {
    expect(shouldShowGeneratorControlPanel({
      type: 'image_generator',
      status: 'failed',
    } as CanvasItem)).toBe(false)
  })

  it('prefers intrinsic image dimensions for export instead of resized canvas display size', () => {
    expect(getImageExportDimensions(baseItem, { width: 1920, height: 1080 })).toEqual({
      width: 1920,
      height: 1080,
    })
  })

  it('falls back to canvas display size when intrinsic image dimensions are unavailable', () => {
    expect(getImageExportDimensions(baseItem, null)).toEqual({
      width: 320,
      height: 180,
    })
  })

  it('restores media to intrinsic size while preserving the item center point', () => {
    expect(getMediaRestoreRect(baseItem, { width: 640, height: 360 })).toEqual({
      x: -40,
      y: -26,
      width: 640,
      height: 360,
    })
  })

  it('clamps regular canvas items below the reserved overlay z-index band', () => {
    expect(clampCanvasStackZIndex(120)).toBe(120)
    expect(clampCanvasStackZIndex(Number.MAX_SAFE_INTEGER)).toBe(2147483000)
    expect(clampCanvasStackZIndex(-Number.MAX_SAFE_INTEGER)).toBe(-2147483000)
  })

  it('returns the next top stack order from the current canvas items', () => {
    expect(getNextCanvasStackZIndex([
      { z_index: 3 },
      { z_index: 18 },
      {},
      { z_index: null },
    ])).toBe(19)
  })
})
