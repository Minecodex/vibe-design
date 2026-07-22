import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { ChevronDown } from 'lucide-react'

import {
  getAvailableVideoResolutions,
  getTailFrameConstraintState,
  getVideoGeneratorCapability,
  getVideoImageInputMode,
  shouldDisableVideoAspectRatio,
  type GeneratorCanvasItemLike,
} from '../generatorCapabilities'
import { buildAnchoredVideoInputs, type AnchoredVideoSourcePlacement } from '../imageAnchoredVideo'
import { formatAspectRatioOptionLabelWithDimensions, type AspectRatioHintLabels, formatResolutionOptionLabel } from '../generatorOptionLabels'
import { getCanvasItemDimensions } from '../mediaDimensions'
import { getAllowedVideoRatios, getAllowedVideoResolutions, getResolvedVideoDurationsFromConfig, getVideoCapabilityFromConfig } from '../videoModelConfig'
import { handleScrollableWheel } from '../scrollableWheel'
import { GeneratorImageSourcePicker } from './GeneratorImageSourcePicker'
import { GeneratorReferenceStrip, useGeneratorReferenceChips } from './GeneratorReferenceStrip'

type VideoModelOption = {
  value: string
  name: string
  provider: string
  providerName: string
  config?: {
    allowed_aspect_ratios?: string[]
    allowed_sizes?: string[]
    dimension_table?: Record<string, Record<string, { width?: number | null; height?: number | null }>>
    dimension_policy?: string
    dimension_source?: string
    allowed_durations?: string[]
    min_duration?: number
    max_duration?: number
  }
}

type ImageAnchoredVideoDraft = {
  sourceImageItemId: string
  sourceImageUrl: string
  prompt: string
  model_name: string
  provider_code: string
  aspect_ratio: string
  duration: string
  resolution?: string
  sourcePlacement: AnchoredVideoSourcePlacement
  reference_images: string[]
  first_frame_image: string
  tail_frame_image: string
}

interface ImageAnchoredVideoPanelProps {
  draft: ImageAnchoredVideoDraft
  draftItem: GeneratorCanvasItemLike
  capability: ReturnType<typeof getVideoGeneratorCapability>
  allowedDurations: string[]
  availableVideoModels: VideoModelOption[]
  isDark: boolean
  t: (key: string, fallback?: string) => string
  amountCents: number | null | undefined
  referenceInputRef: RefObject<HTMLInputElement>
  firstFrameInputRef: RefObject<HTMLInputElement>
  tailFrameInputRef: RefObject<HTMLInputElement>
  onUpdateDraft: (updates: Partial<ImageAnchoredVideoDraft>) => void
  onMoveSourcePlacement: (placement: AnchoredVideoSourcePlacement) => void
  onPreviewImage: (url: string) => void
  onGenerate: () => void
  onPickReferenceFromLibrary: () => void
  onPickFirstFrameFromLibrary: () => void
  onPickTailFrameFromLibrary: () => void
  onPickReferenceFromReferenceGallery?: () => void
  onPickFirstFrameFromReferenceGallery?: () => void
  onPickTailFrameFromReferenceGallery?: () => void
  showSourceDragHint?: boolean
}

function SourceChip({
  imageUrl,
  onPreviewImage,
  label,
}: {
  imageUrl: string
  onPreviewImage: (url: string) => void
  label: string
}) {
  return (
    <div
      draggable
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('text/plain', 'anchored-source-image')
      }}
      onClick={(event) => {
        event.stopPropagation()
        onPreviewImage(imageUrl)
      }}
      style={{
        position: 'relative',
        width: 32,
        height: 32,
        borderRadius: 6,
        overflow: 'hidden',
        border: '1px solid var(--app-primary)',
        flexShrink: 0,
        cursor: 'grab',
        boxShadow: '0 0 0 1px var(--app-focus-ring)',
      }}
    >
      <img src={imageUrl} alt="Source" loading="lazy" decoding="async" draggable={false} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      <div
        style={{
          position: 'absolute',
          inset: 'auto 2px 2px 2px',
          borderRadius: 4,
          backgroundColor: 'var(--app-media-scrim)',
          color: 'var(--app-primary-foreground)',
          fontSize: 8,
          lineHeight: 1.2,
          padding: '1px 3px',
          textAlign: 'center',
        }}
      >
        {label}
      </div>
    </div>
  )
}

export function ImageAnchoredVideoPanel({
  draft,
  draftItem,
  capability,
  allowedDurations,
  availableVideoModels,
  isDark,
  t,
  referenceInputRef,
  firstFrameInputRef,
  tailFrameInputRef,
  onUpdateDraft,
  onMoveSourcePlacement,
  onPreviewImage,
  onGenerate,
  onPickReferenceFromLibrary,
  onPickFirstFrameFromLibrary,
  onPickTailFrameFromLibrary,
  onPickReferenceFromReferenceGallery = () => {},
  onPickFirstFrameFromReferenceGallery = () => {},
  onPickTailFrameFromReferenceGallery = () => {},
  showSourceDragHint = false,
}: ImageAnchoredVideoPanelProps) {
  const [activeDropdown, setActiveDropdown] = useState<'model' | 'resolution' | 'duration' | 'ratio' | null>(null)
  const [draggingSource, setDraggingSource] = useState(false)

  useEffect(() => {
    const handleClick = () => setActiveDropdown(null)
    window.addEventListener('click', handleClick)
    return () => window.removeEventListener('click', handleClick)
  }, [])

  useEffect(() => {
    if (allowedDurations.length > 0 && !allowedDurations.includes(draft.duration)) {
      onUpdateDraft({ duration: allowedDurations[0] })
    }
  }, [allowedDurations, draft.duration, onUpdateDraft])

  const currentModel = availableVideoModels.find((model) => model.value === draft.model_name) || availableVideoModels[0]
  const effectiveInputs = buildAnchoredVideoInputs({
    sourceImageUrl: draft.sourceImageUrl,
    sourcePlacement: draft.sourcePlacement,
    referenceImages: draft.reference_images,
    firstFrameImage: draft.first_frame_image,
    tailFrameImage: draft.tail_frame_image,
  })
  const showRatioSelector = !shouldDisableVideoAspectRatio(capability, draftItem)
  const allowedRatios = getAllowedVideoRatios(currentModel?.config)
  const baseAllowedResolutions = getAllowedVideoResolutions(currentModel?.config)
  const allowedResolutions = getAvailableVideoResolutions(capability, draftItem, baseAllowedResolutions)
  const resolvedResolution = draft.resolution || allowedResolutions[0] || baseAllowedResolutions[0] || '720p'
  const dimensionFallback = {
    videoModel: currentModel?.value || draft.model_name,
    videoProvider: currentModel?.provider || draft.provider_code,
    videoModelConfig: currentModel?.config,
    videoModels: availableVideoModels,
  }
  const tailFrameConstraint = getTailFrameConstraintState(capability, draftItem, resolvedResolution)
  const effectiveReferenceCount = effectiveInputs.referenceImages.length
  const ratioHintLabels: AspectRatioHintLabels = {
    square: t('canvas.generator.ratio_hint_square', '鏂瑰舰'),
    landscape: t('canvas.generator.ratio_hint_landscape', '妯悜'),
    portrait: t('canvas.generator.ratio_hint_portrait', '绔栧悜'),
  }
  const standardSuffix = t('canvas.generator.standard_suffix', '鏍囧噯')

  const dropZoneStyle = (isActive: boolean, disabled?: boolean) => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: 0,
    border: 'none',
    borderRadius: 0,
    backgroundColor: 'transparent',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    boxShadow: 'none',
    outline: isActive ? '1px solid var(--app-focus-ring)' : 'none',
    outlineOffset: 2,
  })

  const referenceUploadDisabled = capability.maxReferenceImages > 0 && effectiveReferenceCount >= capability.maxReferenceImages
  const referenceImagesRef = useRef(draft.reference_images)
  referenceImagesRef.current = draft.reference_images
  const removeReferenceLabel = t('canvas.generator.remove_reference', 'Remove reference')
  const removeFirstFrameLabel = t('canvas.generator.remove_first_frame', 'Remove first frame')
  const removeTailFrameLabel = t('canvas.generator.remove_tail_frame', 'Remove tail frame')
  const referenceImageLabel = t('canvas.generator.reference_image', 'Reference image')
  const firstFrameLabel = t('canvas.generator.first_frame', 'First Frame')
  const tailFrameLabel = t('canvas.generator.tail_frame', 'Tail Frame')
  const referenceChips = useGeneratorReferenceChips({
    imageUrls: draft.reference_images,
    alt: referenceImageLabel,
    removeLabel: removeReferenceLabel,
  })
  const firstFrameChips = useGeneratorReferenceChips({
    imageUrls: draft.sourcePlacement === 'first_frame' || !draft.first_frame_image ? [] : [draft.first_frame_image],
    alt: firstFrameLabel,
    removeLabel: removeFirstFrameLabel,
    idPrefix: 'first:',
  })
  const tailFrameChips = useGeneratorReferenceChips({
    imageUrls: draft.sourcePlacement === 'tail_frame' || !draft.tail_frame_image ? [] : [draft.tail_frame_image],
    alt: tailFrameLabel,
    removeLabel: removeTailFrameLabel,
    idPrefix: 'tail:',
  })
  const handleRemoveReference = useCallback((chipId: string) => {
    const index = Number(chipId.split(':', 1)[0])
    if (!Number.isFinite(index)) return
    const referenceImages = referenceImagesRef.current
    onUpdateDraft({
      reference_images: referenceImages.filter((_, imageIndex) => imageIndex !== index),
    })
  }, [onUpdateDraft])
  const handleRemoveFirstFrame = useCallback(() => {
    onUpdateDraft({ first_frame_image: '' })
  }, [onUpdateDraft])
  const handleRemoveTailFrame = useCallback(() => {
    onUpdateDraft({ tail_frame_image: '' })
  }, [onUpdateDraft])

  useEffect(() => {
    if (allowedResolutions.length > 0 && !allowedResolutions.includes(resolvedResolution)) {
      onUpdateDraft({ resolution: allowedResolutions[0] })
    }
  }, [allowedResolutions, onUpdateDraft, resolvedResolution])

  return (
    <div
      className="nowheel"
      style={{
        width: 720,
        backgroundColor: 'var(--app-glass)',
        borderRadius: 16,
        boxShadow: 'var(--app-shadow-panel)',
        border: '1px solid var(--app-border)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        zIndex: 2147483500,
      }}
      onMouseDown={(event) => event.stopPropagation()}
      onClick={(event) => { event.stopPropagation(); setActiveDropdown(null); }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--app-foreground)' }}>
          {t('canvas.generator.describe_imagination', '鎻忚堪浣犵殑鎯宠薄')}
        </div>
        <div
          style={{
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            borderRadius: 12,
            border: '1px solid var(--app-border)',
            backgroundColor: 'var(--app-control)',
            overflow: 'hidden',
          }}
        >
          <textarea
            value={draft.prompt || ''}
            onChange={(event) => onUpdateDraft({ prompt: event.target.value })}
            placeholder={t('canvas.generator.prompt_placeholder_video')}
            onClick={() => setActiveDropdown(null)}
            style={{
              width: '100%',
              height: 120,
              padding: '16px',
              border: 'none',
              fontSize: 15,
              resize: 'none',
              outline: 'none',
              backgroundColor: 'transparent',
              color: 'var(--app-foreground)',
            }}
          />

          <div
            data-testid="anchored-video-footer"
            data-layout="stacked"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              padding: '12px 16px',
              backgroundColor: 'transparent',
            }}
          >
            {showSourceDragHint && (
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: 'var(--app-foreground-muted)',
                }}
              >
                当前图片按住可拖拽
              </div>
            )}
            {capability.supportsReferenceImages && (draft.sourcePlacement === 'reference' || draft.reference_images.length > 0) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {draft.sourcePlacement === 'reference' && (
                  <SourceChip
                    imageUrl={draft.sourceImageUrl}
                    onPreviewImage={onPreviewImage}
                    label={t('canvas.generator.current_image', '当前图片')}
                  />
                )}
                <GeneratorReferenceStrip
                  chips={referenceChips}
                  isDark={isDark}
                  onPreviewImage={onPreviewImage}
                  onRemove={handleRemoveReference}
                />
              </div>
            )}
            <div
              data-testid="anchored-video-footer-actions"
              data-layout="action-row"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexWrap: 'wrap',
                justifyContent: 'flex-end',
              }}
            >
              {capability.supportsReferenceImages && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div
                    onDragOver={(event) => {
                      if (!capability.supportsReferenceImages || referenceUploadDisabled) return
                      event.preventDefault()
                      setDraggingSource(true)
                    }}
                    onDragLeave={() => setDraggingSource(false)}
                    onDrop={(event) => {
                      event.preventDefault()
                      setDraggingSource(false)
                      if (referenceUploadDisabled) return
                      onMoveSourcePlacement('reference')
                    }}
                    style={dropZoneStyle(draggingSource && draft.sourcePlacement !== 'reference', referenceUploadDisabled)}
                  >
                    <GeneratorImageSourcePicker
                      isDark={isDark}
                      label={t('canvas.generator.reference_image', '参考图片')}
                      countLabel={`${t('canvas.generator.reference_image', '参考图片')}${capability.maxReferenceImages > 1 ? ` ${effectiveReferenceCount}/${capability.maxReferenceImages}` : ''}`}
                      localLabel={t('canvas.generator.local_image', '本地图片')}
                      libraryLabel={t('canvas.generator.source_asset_library', '素材库')}
                      referenceLibraryLabel={t('canvas.generator.reference_gallery', '参考图库')}
                      active={effectiveReferenceCount > 0 && !referenceUploadDisabled}
                      localDisabled={referenceUploadDisabled}
                      libraryDisabled={referenceUploadDisabled}
                      referenceLibraryDisabled={referenceUploadDisabled}
                      onPickLocal={() => referenceInputRef.current?.click()}
                      onPickFromLibrary={onPickReferenceFromLibrary}
                      onPickFromReferenceLibrary={onPickReferenceFromReferenceGallery}
                    />
                  </div>
                </div>
              )}

              {capability.supportsFirstFrame && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {draft.sourcePlacement === 'first_frame' ? (
                    <SourceChip
                      imageUrl={draft.sourceImageUrl}
                      onPreviewImage={onPreviewImage}
                      label={t('canvas.generator.current_image', '当前图片')}
                    />
                  ) : firstFrameChips.length > 0 ? (
                    <GeneratorReferenceStrip
                      chips={firstFrameChips}
                      isDark={isDark}
                      onPreviewImage={onPreviewImage}
                      onRemove={handleRemoveFirstFrame}
                    />
                  ) : null}

                  <div
                    onDragOver={(event) => {
                      event.preventDefault()
                      setDraggingSource(true)
                    }}
                    onDragLeave={() => setDraggingSource(false)}
                    onDrop={(event) => {
                      event.preventDefault()
                      setDraggingSource(false)
                      onMoveSourcePlacement('first_frame')
                    }}
                    style={dropZoneStyle(draggingSource && draft.sourcePlacement !== 'first_frame')}
                  >
                    <GeneratorImageSourcePicker
                      isDark={isDark}
                      label={t('canvas.generator.first_frame')}
                      localLabel={t('canvas.generator.local_image', '本地图片')}
                      libraryLabel={t('canvas.generator.source_asset_library', '素材库')}
                      referenceLibraryLabel={t('canvas.generator.reference_gallery', '参考图库')}
                      active={draft.sourcePlacement === 'first_frame' || Boolean(draft.first_frame_image)}
                      onPickLocal={() => firstFrameInputRef.current?.click()}
                      onPickFromLibrary={onPickFirstFrameFromLibrary}
                      onPickFromReferenceLibrary={onPickFirstFrameFromReferenceGallery}
                    />
                  </div>
                </div>
              )}

              {capability.supportsTailFrame && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {draft.sourcePlacement === 'tail_frame' ? (
                    <SourceChip
                      imageUrl={draft.sourceImageUrl}
                      onPreviewImage={onPreviewImage}
                      label={t('canvas.generator.current_image', '当前图片')}
                    />
                  ) : tailFrameChips.length > 0 ? (
                    <GeneratorReferenceStrip
                      chips={tailFrameChips}
                      isDark={isDark}
                      onPreviewImage={onPreviewImage}
                      onRemove={handleRemoveTailFrame}
                    />
                  ) : null}

                  <div
                    onDragOver={(event) => {
                      if (!tailFrameConstraint.enabled) return
                      event.preventDefault()
                      setDraggingSource(true)
                    }}
                    onDragLeave={() => setDraggingSource(false)}
                    onDrop={(event) => {
                      if (!tailFrameConstraint.enabled) return
                      event.preventDefault()
                      setDraggingSource(false)
                      onMoveSourcePlacement('tail_frame')
                    }}
                    style={dropZoneStyle(draggingSource && draft.sourcePlacement !== 'tail_frame', !tailFrameConstraint.enabled)}
                  >
                    <GeneratorImageSourcePicker
                      isDark={isDark}
                      label={t('canvas.generator.tail_frame')}
                      localLabel={t('canvas.generator.local_image', '本地图片')}
                      libraryLabel={t('canvas.generator.source_asset_library', '素材库')}
                      referenceLibraryLabel={t('canvas.generator.reference_gallery', '参考图库')}
                      active={draft.sourcePlacement === 'tail_frame' || Boolean(draft.tail_frame_image)}
                      disabled={!tailFrameConstraint.enabled}
                      localDisabled={!tailFrameConstraint.enabled}
                      libraryDisabled={!tailFrameConstraint.enabled}
                      referenceLibraryDisabled={!tailFrameConstraint.enabled}
                      onPickLocal={() => tailFrameInputRef.current?.click()}
                      onPickFromLibrary={onPickTailFrameFromLibrary}
                      onPickFromReferenceLibrary={onPickTailFrameFromReferenceGallery}
                    />
                  </div>
                </div>
              )}
            </div>

            <div
              onClick={(event) => {
                event.stopPropagation()
                onGenerate()
              }}
              style={{
                height: 38,
                borderRadius: 12,
                backgroundColor: 'var(--app-primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: 'var(--app-primary-foreground)',
                padding: '0 16px',
                gap: 6,
                boxShadow: 'var(--app-shadow-control)',
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ fontSize: 16 }}>Go</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{t('canvas.generator.generate_now', '绔嬪嵆鐢熸垚')}</span>
            </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${showRatioSelector ? 4 : 3}, 1fr)`, gap: 16, position: 'relative', zIndex: 2147483501 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
            {t('canvas.generator.model_label', '鐢熸垚妯″瀷')}
          </div>
          <div style={{ position: 'relative', zIndex: activeDropdown === 'ratio' ? 2147483643 : 'auto' }}>
            <div
              onClick={(event) => {
                event.stopPropagation()
                setActiveDropdown(activeDropdown === 'model' ? null : 'model')
              }}
              style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}
            >
              <span style={{ fontWeight: 500, color: 'var(--app-foreground)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {currentModel?.name || draft.model_name}
              </span>
              <ChevronDown size={18} color="var(--app-foreground-subtle)" />
            </div>
            {activeDropdown === 'model' && (
              <div style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)', padding: 8, width: '100%', minWidth: 200, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 200, overflowY: 'auto' }}>
                {availableVideoModels.map((model) => (
                  <div
                    key={model.value}
                    onClick={(event) => {
                      event.stopPropagation()
                      const nextCapability = getVideoCapabilityFromConfig(model.config, model.value)
                      const updates: Partial<ImageAnchoredVideoDraft> = {
                        model_name: model.value,
                        provider_code: model.provider,
                      }
                      const nextAllowedRatios = getAllowedVideoRatios(model.config)
                      const nextAllowedResolutions = getAllowedVideoResolutions(model.config)
                      const nextAllowedDurations = getResolvedVideoDurationsFromConfig(
                        availableVideoModels,
                        { ...draft, ...updates },
                        model.value,
                        model.provider,
                        model.config?.allowed_durations,
                      )
                      const currentResolution = draft.resolution || nextAllowedResolutions[0] || '720p'
                      if (!nextAllowedRatios.includes(draft.aspect_ratio)) {
                        updates.aspect_ratio = nextAllowedRatios[0] || '16:9'
                      }
                      if (!nextAllowedResolutions.includes(currentResolution)) {
                        updates.resolution = nextAllowedResolutions[0] || '720p'
                      }
                      if (nextAllowedDurations.length > 0 && !nextAllowedDurations.includes(draft.duration)) {
                        updates.duration = nextAllowedDurations[0]
                      }
                      if (!nextCapability.supportsReferenceImages && draft.sourcePlacement === 'reference') {
                        updates.sourcePlacement = nextCapability.supportsFirstFrame ? 'first_frame' : 'reference'
                        updates.reference_images = []
                      } else if (nextCapability.supportsReferenceImages && draft.reference_images.length > nextCapability.maxReferenceImages) {
                        updates.reference_images = draft.reference_images.slice(0, nextCapability.maxReferenceImages)
                      }
                      if (!nextCapability.supportsFirstFrame) {
                        updates.first_frame_image = ''
                        if (draft.sourcePlacement === 'first_frame') {
                          updates.sourcePlacement = nextCapability.supportsReferenceImages ? 'reference' : 'first_frame'
                        }
                      }
                      if (!nextCapability.supportsTailFrame) {
                        updates.tail_frame_image = ''
                        if (draft.sourcePlacement === 'tail_frame') {
                          updates.sourcePlacement = nextCapability.supportsReferenceImages ? 'reference' : 'first_frame'
                        }
                      }
                      const currentInputMode = getVideoImageInputMode(capability, draftItem)
                      const nextDraft = { ...draft, ...updates }
                      const nextEffectiveInputs = buildAnchoredVideoInputs({
                        sourceImageUrl: nextDraft.sourceImageUrl,
                        sourcePlacement: nextDraft.sourcePlacement,
                        referenceImages: nextDraft.reference_images,
                        firstFrameImage: nextDraft.first_frame_image,
                        tailFrameImage: nextDraft.tail_frame_image,
                      })
                      const nextDraftItem = {
                        ...draftItem,
                        ...nextDraft,
                        reference_images: nextEffectiveInputs.referenceImages,
                        reference_image: nextEffectiveInputs.referenceImages[0] || '',
                        first_frame_image: nextEffectiveInputs.firstFrameImage,
                        tail_frame_image: nextEffectiveInputs.tailFrameImage,
                      }
                      const nextAllowedResolutionOptions = getAvailableVideoResolutions(
                        nextCapability,
                        nextDraftItem,
                        nextAllowedResolutions,
                      )
                      if (nextAllowedResolutionOptions.length > 0) {
                        const nextResolution = nextDraft.resolution || currentResolution
                        if (!nextAllowedResolutionOptions.includes(nextResolution)) {
                          updates.resolution = nextAllowedResolutionOptions[0]
                        }
                      }
                      const nextSourcePlacement = updates.sourcePlacement || draft.sourcePlacement
                      if (nextCapability.imageModesConflict) {
                        if (currentInputMode === 'reference' && nextCapability.supportsReferenceImages) {
                          updates.first_frame_image = ''
                          updates.tail_frame_image = ''
                        } else {
                          updates.reference_images = []
                        }
                      }
                      const constrainedDraft = { ...draft, ...updates }
                      const constrainedEffectiveInputs = buildAnchoredVideoInputs({
                        sourceImageUrl: constrainedDraft.sourceImageUrl,
                        sourcePlacement: constrainedDraft.sourcePlacement,
                        referenceImages: constrainedDraft.reference_images,
                        firstFrameImage: constrainedDraft.first_frame_image,
                        tailFrameImage: constrainedDraft.tail_frame_image,
                      })
                      const constrainedDraftItem = {
                        ...draftItem,
                        ...constrainedDraft,
                        reference_images: constrainedEffectiveInputs.referenceImages,
                        reference_image: constrainedEffectiveInputs.referenceImages[0] || '',
                        first_frame_image: constrainedEffectiveInputs.firstFrameImage,
                        tail_frame_image: constrainedEffectiveInputs.tailFrameImage,
                      }
                      const nextTailFrameConstraint = getTailFrameConstraintState(
                        nextCapability,
                        constrainedDraftItem,
                        constrainedDraft.resolution || currentResolution,
                      )
                      if (!nextTailFrameConstraint.enabled) {
                        if (nextSourcePlacement === 'tail_frame') {
                          updates.sourcePlacement = nextCapability.supportsFirstFrame ? 'first_frame' : 'reference'
                        }
                        updates.tail_frame_image = ''
                      }
                      onUpdateDraft(updates)
                      setActiveDropdown(null)
                    }}
                    style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 2, backgroundColor: draft.model_name === model.value ? 'var(--app-control-selected)' : 'transparent' }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.backgroundColor = draft.model_name === model.value ? 'var(--app-control-selected)' : 'var(--app-control-hover)'
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.backgroundColor = draft.model_name === model.value ? 'var(--app-control-selected)' : 'transparent'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--app-foreground)' }}>{model.name}</span>
                      {draft.model_name === model.value && <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: 'var(--app-primary)' }} />}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--app-foreground-subtle)' }}>{model.providerName}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
            {t('canvas.generator.resolution_label', '绮惧害璁剧疆')}
          </div>
          <div style={{ position: 'relative' }}>
            <div
              onClick={(event) => {
                event.stopPropagation()
                setActiveDropdown(activeDropdown === 'resolution' ? null : 'resolution')
              }}
              style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}
            >
              <span style={{ fontWeight: 500, color: 'var(--app-foreground)' }}>
                {formatResolutionOptionLabel(resolvedResolution, standardSuffix)}
              </span>
              <ChevronDown size={18} color="var(--app-foreground-subtle)" />
            </div>
            {activeDropdown === 'resolution' && (
              <div style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: 8, width: '100%', minWidth: 100, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {allowedResolutions.map((resolution) => (
                  <div
                    key={resolution}
                    onClick={(event) => {
                      event.stopPropagation()
                      onUpdateDraft({ resolution })
                      setActiveDropdown(null)
                    }}
                    style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: 'var(--app-foreground)', backgroundColor: resolvedResolution === resolution ? 'var(--app-control-selected)' : 'transparent' }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.backgroundColor = resolvedResolution === resolution ? 'var(--app-control-selected)' : 'var(--app-control-hover)'
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.backgroundColor = resolvedResolution === resolution ? 'var(--app-control-selected)' : 'transparent'
                    }}
                  >
                    {formatResolutionOptionLabel(resolution, standardSuffix)}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
            {t('canvas.generator.duration_label', '鏃堕暱璁剧疆')}
          </div>
          <div style={{ position: 'relative' }}>
            <div
              onClick={(event) => {
                event.stopPropagation()
                setActiveDropdown(activeDropdown === 'duration' ? null : 'duration')
              }}
              style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}
            >
              <span style={{ fontWeight: 500, color: 'var(--app-foreground)' }}>{draft.duration}</span>
              <ChevronDown size={18} color="var(--app-foreground-subtle)" />
            </div>
            {activeDropdown === 'duration' && (
              <div
                onWheel={handleScrollableWheel}
                style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: 8, width: '100%', minWidth: 100, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 200, overflowY: 'auto' }}
              >
                {allowedDurations.map((duration) => (
                  <div
                    key={duration}
                    onClick={(event) => {
                      event.stopPropagation()
                      onUpdateDraft({ duration })
                      setActiveDropdown(null)
                    }}
                    style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: 'var(--app-foreground)', backgroundColor: draft.duration === duration ? 'var(--app-control-selected)' : 'transparent' }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.backgroundColor = draft.duration === duration ? 'var(--app-control-selected)' : 'var(--app-control-hover)'
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.backgroundColor = draft.duration === duration ? 'var(--app-control-selected)' : 'transparent'
                    }}
                  >
                    {duration}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {showRatioSelector && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
              {t('canvas.generator.ratio_label', '鐢诲竷姣斾緥')}
            </div>
            <div style={{ position: 'relative' }}>
              <div
                onClick={(event) => {
                  event.stopPropagation()
                  setActiveDropdown(activeDropdown === 'ratio' ? null : 'ratio')
                }}
              style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}
            >
              <span style={{ fontWeight: 500, color: 'var(--app-foreground)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
                {formatAspectRatioOptionLabelWithDimensions(
                  draft.aspect_ratio,
                  ratioHintLabels,
                    getCanvasItemDimensions({
                      type: 'video_generator',
                      aspect_ratio: draft.aspect_ratio,
                      provider_code: draft.provider_code,
                      resolution: resolvedResolution,
                    }, dimensionFallback),
                )}
              </span>
              <div style={{ flexShrink: 0, marginLeft: 8 }}>
                <ChevronDown size={18} color="var(--app-foreground-subtle)" />
              </div>
            </div>
            {activeDropdown === 'ratio' && (
              <div data-testid="anchored-video-ratio-dropdown" onWheel={handleScrollableWheel} style={{ position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: 8, width: '100%', minWidth: 120, zIndex: 2147483503, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 280, overflowY: 'auto' }}>
                {allowedRatios.map((ratio) => (
                    <div
                      key={ratio}
                      onClick={(event) => {
                        event.stopPropagation()
                        onUpdateDraft({ aspect_ratio: ratio })
                        setActiveDropdown(null)
                      }}
                      style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: 'var(--app-foreground)', backgroundColor: draft.aspect_ratio === ratio ? 'var(--app-control-selected)' : 'transparent' }}
                      onMouseEnter={(event) => {
                        event.currentTarget.style.backgroundColor = draft.aspect_ratio === ratio ? 'var(--app-control-selected)' : 'var(--app-control-hover)'
                      }}
                      onMouseLeave={(event) => {
                        event.currentTarget.style.backgroundColor = draft.aspect_ratio === ratio ? 'var(--app-control-selected)' : 'transparent'
                      }}
                    >
                      {formatAspectRatioOptionLabelWithDimensions(
                        ratio,
                        ratioHintLabels,
                        getCanvasItemDimensions({
                          type: 'video_generator',
                          aspect_ratio: ratio,
                          provider_code: draft.provider_code,
                          resolution: resolvedResolution,
                        }, dimensionFallback),
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


