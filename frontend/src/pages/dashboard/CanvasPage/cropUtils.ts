export type CropPresetKind = 'general' | 'platform'

export interface CropPreset {
  id: string
  label: string
  width: number
  height: number
  kind: CropPresetKind
}

export interface CropPresetGroup {
  id: string
  label: string
  presets: CropPreset[]
}

export interface CropArea {
  x: number
  y: number
  width: number
  height: number
}

export interface CropRect extends CropArea {}

export const CROP_PRESET_GROUPS: CropPresetGroup[] = [
  {
    id: 'general',
    label: '通用',
    presets: [
      { id: 'general-1-1', label: '1:1', width: 1, height: 1, kind: 'general' },
      { id: 'general-3-4', label: '3:4', width: 3, height: 4, kind: 'general' },
      { id: 'general-2-3', label: '2:3', width: 2, height: 3, kind: 'general' },
      { id: 'general-9-16', label: '9:16', width: 9, height: 16, kind: 'general' },
      { id: 'general-4-3', label: '4:3', width: 4, height: 3, kind: 'general' },
      { id: 'general-3-2', label: '3:2', width: 3, height: 2, kind: 'general' },
      { id: 'general-16-9', label: '16:9', width: 16, height: 9, kind: 'general' },
    ],
  },
  {
    id: 'instagram',
    label: 'Instagram',
    presets: [
      { id: 'instagram-feed', label: '图文动态 (1:1)', width: 1080, height: 1080, kind: 'platform' },
      { id: 'instagram-story', label: '快拍/竖屏 (9:16)', width: 1080, height: 1920, kind: 'platform' },
      { id: 'instagram-portrait', label: '垂直动态 (4:5)', width: 1080, height: 1350, kind: 'platform' },
    ],
  },
  {
    id: 'facebook',
    label: 'Facebook',
    presets: [
      { id: 'facebook-post', label: '动态消息 (1:1)', width: 1200, height: 1200, kind: 'platform' },
      { id: 'facebook-cover', label: '封面图片', width: 1640, height: 924, kind: 'platform' },
      { id: 'facebook-ad', label: '广告图片 (1.91:1)', width: 1200, height: 628, kind: 'platform' },
    ],
  },
  {
    id: 'tiktok',
    label: 'TikTok',
    presets: [
      { id: 'tiktok-video', label: '竖屏视频 (9:16)', width: 1080, height: 1920, kind: 'platform' },
      { id: 'tiktok-avatar', label: '头像 (1:1)', width: 200, height: 200, kind: 'platform' },
    ],
  },
  {
    id: 'youtube',
    label: 'YouTube',
    presets: [
      { id: 'youtube-thumbnail', label: '视频缩略图', width: 1280, height: 720, kind: 'platform' },
      { id: 'youtube-banner', label: '频道横幅', width: 2560, height: 1440, kind: 'platform' },
    ],
  },
  {
    id: 'linkedin',
    label: 'LinkedIn',
    presets: [
      { id: 'linkedin-profile-cover', label: '个人封面', width: 1584, height: 396, kind: 'platform' },
      { id: 'linkedin-company-cover', label: '公司封面', width: 1128, height: 191, kind: 'platform' },
      { id: 'linkedin-post', label: '动态 (1:1)', width: 1200, height: 1200, kind: 'platform' },
    ],
  },
  {
    id: 'twitter',
    label: 'Twitter',
    presets: [
      { id: 'twitter-header', label: '横幅封面', width: 1500, height: 500, kind: 'platform' },
      { id: 'twitter-post', label: '动态图片 (16:9)', width: 1200, height: 675, kind: 'platform' },
    ],
  },
  {
    id: 'xiaohongshu',
    label: '小红书',
    presets: [
      { id: 'xiaohongshu-feed', label: '图文封面 (3:4)', width: 1080, height: 1440, kind: 'platform' },
    ],
  },
  {
    id: 'kuaishou',
    label: '快手',
    presets: [
      { id: 'kuaishou-feed', label: '竖版封面 (9:16)', width: 1080, height: 1920, kind: 'platform' },
    ],
  },
  {
    id: 'douyin',
    label: '抖音',
    presets: [
      { id: 'douyin-feed', label: '竖版封面 (9:16)', width: 1080, height: 1920, kind: 'platform' },
    ],
  },
]

export function getPresetById(groups: CropPresetGroup[], presetId: string): CropPreset | undefined {
  for (const group of groups) {
    const preset = group.presets.find((entry) => entry.id === presetId)
    if (preset) return preset
  }
  return undefined
}

function getPresetRatio(preset: CropPreset): number {
  return preset.width / preset.height
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

export function createInitialCropRect(args: {
  sourceWidth: number
  sourceHeight: number
}): CropRect {
  const { sourceWidth, sourceHeight } = args
  return {
    x: 0,
    y: 0,
    width: Math.max(1, sourceWidth),
    height: Math.max(1, sourceHeight),
  }
}

export function createCenteredCropRectFromPreset(args: {
  sourceWidth: number
  sourceHeight: number
  preset: CropPreset
}): CropRect {
  return computeCropArea(args)
}

export function clampCropRect(args: {
  rect: CropRect
  sourceWidth: number
  sourceHeight: number
  minWidth?: number
  minHeight?: number
}): CropRect {
  const { rect, sourceWidth, sourceHeight, minWidth = 1, minHeight = 1 } = args
  const maxWidth = Math.max(minWidth, sourceWidth)
  const maxHeight = Math.max(minHeight, sourceHeight)
  const width = clamp(rect.width, minWidth, maxWidth)
  const height = clamp(rect.height, minHeight, maxHeight)
  const x = clamp(rect.x, 0, Math.max(0, sourceWidth - width))
  const y = clamp(rect.y, 0, Math.max(0, sourceHeight - height))

  return {
    x,
    y,
    width,
    height,
  }
}

export function resizeCropRectFromDimensions(args: {
  rect: CropRect
  nextWidth?: number
  nextHeight?: number
  sourceWidth: number
  sourceHeight: number
  minWidth?: number
  minHeight?: number
}): CropRect {
  const {
    rect,
    nextWidth,
    nextHeight,
    sourceWidth,
    sourceHeight,
    minWidth = 1,
    minHeight = 1,
  } = args

  const width = clamp(nextWidth ?? rect.width, minWidth, sourceWidth)
  const height = clamp(nextHeight ?? rect.height, minHeight, sourceHeight)
  const centerX = rect.x + rect.width / 2
  const centerY = rect.y + rect.height / 2

  return clampCropRect({
    rect: {
      x: centerX - width / 2,
      y: centerY - height / 2,
      width,
      height,
    },
    sourceWidth,
    sourceHeight,
    minWidth,
    minHeight,
  })
}

export function moveCropRect(args: {
  rect: CropRect
  deltaX: number
  deltaY: number
  sourceWidth: number
  sourceHeight: number
}): CropRect {
  const { rect, deltaX, deltaY, sourceWidth, sourceHeight } = args

  return clampCropRect({
    rect: {
      x: rect.x + deltaX,
      y: rect.y + deltaY,
      width: rect.width,
      height: rect.height,
    },
    sourceWidth,
    sourceHeight,
    minWidth: rect.width,
    minHeight: rect.height,
  })
}

export function getCropCommitMode(args: {
  sourceWidth: number
  sourceHeight: number
  preset: CropPreset
}): 'crop' | 'noop' {
  const { sourceWidth, sourceHeight, preset } = args
  if (preset.kind === 'general') return 'crop'
  if (sourceWidth < preset.width || sourceHeight < preset.height) return 'noop'
  return 'crop'
}

export function computeCropArea(args: {
  sourceWidth: number
  sourceHeight: number
  preset: CropPreset
}): CropArea {
  const { sourceWidth, sourceHeight, preset } = args
  const sourceRatio = sourceWidth / sourceHeight
  const targetRatio = getPresetRatio(preset)

  if (sourceRatio > targetRatio) {
    const width = sourceHeight * targetRatio
    return {
      x: (sourceWidth - width) / 2,
      y: 0,
      width,
      height: sourceHeight,
    }
  }

  const height = sourceWidth / targetRatio
  return {
    x: 0,
    y: (sourceHeight - height) / 2,
    width: sourceWidth,
    height,
  }
}

export function getCropDisplaySize(args: {
  sourceWidth: number
  sourceHeight: number
  preset: CropPreset
}): { width: number; height: number } {
  const { sourceWidth, sourceHeight, preset } = args
  if (preset.kind === 'platform') {
    return {
      width: preset.width,
      height: preset.height,
    }
  }

  const cropArea = computeCropArea({ sourceWidth, sourceHeight, preset })
  return {
    width: cropArea.width,
    height: cropArea.height,
  }
}

export function computePreviewFrame(args: {
  displayWidth: number
  displayHeight: number
  preset: CropPreset
  mode: 'crop' | 'noop'
}): CropArea {
  const { displayWidth, displayHeight, preset, mode } = args
  const targetRatio = getPresetRatio(preset)
  const displayRatio = displayWidth / displayHeight

  if (mode === 'crop') {
    if (displayRatio > targetRatio) {
      const width = displayHeight * targetRatio
      return {
        x: (displayWidth - width) / 2,
        y: 0,
        width,
        height: displayHeight,
      }
    }

    const height = displayWidth / targetRatio
    return {
      x: 0,
      y: (displayHeight - height) / 2,
      width: displayWidth,
      height,
    }
  }

  if (displayRatio > targetRatio) {
    const height = displayWidth / targetRatio
    return {
      x: 0,
      y: (displayHeight - height) / 2,
      width: displayWidth,
      height,
    }
  }

  const width = displayHeight * targetRatio
  return {
    x: (displayWidth - width) / 2,
    y: 0,
    width,
    height: displayHeight,
  }
}
