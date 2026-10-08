import type { ComponentProps, CSSProperties, Dispatch, MouseEvent, ReactNode, RefObject, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'
import type { CanvasWorkspaceTextRenderItem } from './CanvasWorkspaceTextRenderItem'
import type { ImageAnchoredImagePanel } from './ImageAnchoredImagePanel'
import type { ImageAnchoredVideoPanel } from './ImageAnchoredVideoPanel'
import type { CropDragState, CropHandle, CropPanelState, ActiveDropdownState, MediaResizeState, BrushResizeState } from '../types'
import type { CanvasRenderSnapshot } from '../canvasRenderModel'
import type { ModifierState } from '../gestureMode'
import type { CropPresetGroup, CropRect } from '../cropUtils'
import type { ImageModelRegistryConfig } from '../imageModelConfig'
import type { VideoModelRegistryConfig } from '../videoModelConfig'
import type { ImageGeneratorCapability, VideoGeneratorCapability, TailFrameConstraintReason } from '../generatorCapabilities'
import type { getCanvasSelectionContainerOverflow } from '../selectionStyles'
import type { getMediaDisplayInitializationUpdate } from '../mediaSelectionResize'
import type { getTextRedrawExtractingBadgeStyle } from '../textRedrawUi'
import type { AspectRatioHintLabels, formatAspectRatioOptionLabelWithDimensions, formatResolutionOptionLabel } from '../generatorOptionLabels'
import type { isMarkModifierPressed } from '../gestureMode'
import type { shouldShowGeneratorControlPanel } from '../imageActions'

type TextProps = ComponentProps<typeof CanvasWorkspaceTextRenderItem>
type ImagePanelProps = ComponentProps<typeof ImageAnchoredImagePanel>
type VideoPanelProps = ComponentProps<typeof ImageAnchoredVideoPanel>
export type CanvasModelConfig = ImageModelRegistryConfig & VideoModelRegistryConfig
export type CanvasModelOption = { value: string; provider: string; name: string; providerName: string; isBuiltin?: boolean; config?: CanvasModelConfig }
export type GeneratorAssetContext =
  | { type: 'canvas-item'; itemId: string; target: 'reference' | 'first_frame' | 'tail_frame' }
  | { type: 'anchored-image'; target: 'reference' }
  | { type: 'anchored-video'; target: 'reference' | 'first_frame' | 'tail_frame' }

export interface CanvasWorkspaceRenderProps extends Omit<TextProps,
  'item' | 'normalizedTextItem' | 'isHidden' | 'isItemSelected' | 'actualWidth' | 'actualHeight' | 'mediaSelectionMetrics' | 'setContextMenu'> {
  setContextMenu: (menu: { x: number; y: number; type?: 'item' | 'canvas' } | null) => void
  setSelectedItems: (items: string[]) => void
  zoom: number
  updateItem: (id: string, updates: Partial<CanvasItem>) => void
  setHoveredMarkableImageId: Dispatch<SetStateAction<string | null>>
  getItemDims: (item: CanvasItem) => { width: number; height: number }
  MARK_CURSOR: string
  imageDetailItemId: string | null
  isMarkModifierPressed: typeof isMarkModifierPressed
  addMark: (item: CanvasItem, event: MouseEvent<HTMLDivElement>) => void
  handleAppendImageMentionToChat: (id: string) => void
  cropState: CropPanelState | null
  cropDragState: CropDragState | null
  getCanvasSelectionContainerOverflow: typeof getCanvasSelectionContainerOverflow
  activeVideoPreviewItemId?: string | null
  getMediaDisplayInitializationUpdate: typeof getMediaDisplayInitializationUpdate
  textRedrawExtractingItemIds: Set<string>
  getTextRedrawExtractingBadgeStyle: (args: Parameters<typeof getTextRedrawExtractingBadgeStyle>[0]) => CSSProperties
  t: TFunction
  handleCropMoveMouseDown: (event: MouseEvent<HTMLDivElement>) => void
  handleCropHandleMouseDown: (handle: CropHandle, event: MouseEvent<HTMLDivElement>) => void
  setMediaResizeState: (state: MediaResizeState) => void
  renderSelectionHandles: () => ReactNode
  marks: CanvasMark[]
  shouldShowGeneratorControlPanel: typeof shouldShowGeneratorControlPanel
  setActiveDropdown: Dispatch<SetStateAction<ActiveDropdownState | null>>
  referenceImageInputRef: RefObject<HTMLInputElement>
  firstFrameImageInputRef: RefObject<HTMLInputElement>
  tailFrameImageInputRef: RefObject<HTMLInputElement>
  openGeneratorAssetLibrary: (context: GeneratorAssetContext) => void
  openGeneratorReferenceGallery: (context: GeneratorAssetContext) => void
  handleGenerateImage: (id: string) => void
  handleGenerateVideo: (id: string) => void
  getItemAmountCents: (item: CanvasItem) => number | null | undefined
  formatResolutionOptionLabel: typeof formatResolutionOptionLabel
  standardSuffix: string
  imageRes: string
  videoQuality: string
  videoDuration: string
  normalizeReferenceImages: typeof import('../generatorCapabilities').normalizeReferenceImages
  withReferenceImages: (images: string[]) => Partial<CanvasItem>
  getImageGeneratorCapability: typeof import('../generatorCapabilities').getImageGeneratorCapability
  getResolvedVideoDurations: (item: CanvasItem, overrides?: Partial<CanvasItem>, modelName?: string, durations?: string[]) => string[]
  imageRatio: string
  videoAspect: string
  ratioHintLabels: AspectRatioHintLabels
  formatAspectRatioOptionLabelWithDimensions: typeof formatAspectRatioOptionLabelWithDimensions
  availableImageModels: CanvasModelOption[]
  availableVideoModels: CanvasModelOption[]
  imageModel: string
  imageProvider: string
  videoModel: string
  videoProvider: string
  cropCommitMode: string | null
  handleCropDimensionChange: (dimension: 'width' | 'height', value: string) => void
  CROP_PRESET_GROUPS: CropPresetGroup[]
  setCropExpandedGroups: Dispatch<SetStateAction<Record<string, boolean>>>
  cropExpandedGroups: Record<string, boolean>
  handleSelectCropPreset: (id: string) => void
  setCropState: Dispatch<SetStateAction<CropPanelState | null>>
  handleApplyCrop: () => void
  imageAnchoredImageDraft: ImagePanelProps['draft'] | null
  imageAnchoredImageDraftItem: CanvasItem | null
  anchoredImageReferenceInputRef: ImagePanelProps['referenceInputRef']
  updateImageAnchoredImageDraft: ImagePanelProps['onUpdateDraft']
  setPreviewImageUrl: (url: string) => void
  handleGenerateAnchoredImage: ImagePanelProps['onGenerate']
  imageAnchoredVideoDraft: VideoPanelProps['draft'] | null
  imageAnchoredVideoDraftItem: CanvasItem | null
  imageAnchoredVideoCapability: VideoGeneratorCapability | null
  imageAnchoredVideoAllowedDurations: string[]
  anchoredReferenceImageInputRef: VideoPanelProps['referenceInputRef']
  anchoredFirstFrameImageInputRef: VideoPanelProps['firstFrameInputRef']
  anchoredTailFrameImageInputRef: VideoPanelProps['tailFrameInputRef']
  updateImageAnchoredVideoDraft: VideoPanelProps['onUpdateDraft']
  handleMoveAnchoredVideoSourcePlacement: VideoPanelProps['onMoveSourcePlacement']
  handleGenerateAnchoredVideo: VideoPanelProps['onGenerate']
}

export interface ComputedMediaRenderProps {
  item: CanvasItem
  isHidden?: boolean
  isImageGroup: boolean
  isMediaAsset: boolean
  isGenerator: boolean
  isHoverOnlyFailedVideo: boolean
  actualWidth: number
  actualHeight: number
  isModelDropdownOpen: boolean
  isResDropdownOpen: boolean
  isVideoResolutionDropdownOpen: boolean
  isDurationDropdownOpen: boolean
  isRatioDropdownOpen: boolean
  isMarkableImage: boolean
  isTransientMarkMode: boolean
  isActiveCropItem: boolean
  isItemSelected: boolean
  mediaSelectionMetrics: TextProps['mediaSelectionMetrics']
  shouldShowMediaSelectionOverlay: boolean
  cropPreviewFrame: CropRect | null
  activeCropOutputSize: { width: number; height: number } | null
  cropPanelOffset: { left: number; top: number } | null
  currentModel: CanvasModelOption | undefined
  currentConfig: CanvasModelConfig | undefined
  imageCapability: ImageGeneratorCapability | null
  videoCapability: VideoGeneratorCapability | null
  allowedVideoDurations: string[]
  allowedVideoResolutions: string[]
  tailFrameConstraint: { enabled: boolean; reason: TailFrameConstraintReason }
  referenceImages: string[]
  showReferenceButton: boolean
  showFirstFrameButton: boolean
  showTailFrameButton: boolean
  showRatioSelector: boolean
  optionColumnCount: number
}

export type CanvasWorkspaceMediaRenderItemProps = CanvasWorkspaceRenderProps & ComputedMediaRenderProps

export interface CanvasWorkspaceItemLayerProps extends CanvasWorkspaceRenderProps {
  canvasRef: RefObject<HTMLDivElement>
  offset: { x: number; y: number }
  activeDropdown: ActiveDropdownState | null
  hoveredMarkableImageId: string | null
  isTransientMarkModeActive: typeof import('../gestureMode').isTransientMarkModeActive
  markModifierState: ModifierState
  selectedSingleItemRect: { left: number; top: number; width: number; height: number } | null
  getMediaSelectionOverlayMetrics: (zoom: number) => TextProps['mediaSelectionMetrics']
  isHoverOnlyFailedVideoTask: typeof import('../imageAnchoredVideo').isHoverOnlyFailedVideoTask
  getResolvedImageCapability: (item: CanvasItem) => ImageGeneratorCapability | null
  getResolvedVideoCapability: (item: CanvasItem) => VideoGeneratorCapability | null
  getItemReferenceImages: (item: CanvasItem) => string[]
  shouldDisableVideoAspectRatio: typeof import('../generatorCapabilities').shouldDisableVideoAspectRatio
  getVideoGeneratorCapability: typeof import('../generatorCapabilities').getVideoGeneratorCapability
  setBrushResizeState: (state: BrushResizeState) => void
  isSceneReady?: boolean
  renderSnapshot?: CanvasRenderSnapshot
  useWebGLRenderer?: boolean
}
