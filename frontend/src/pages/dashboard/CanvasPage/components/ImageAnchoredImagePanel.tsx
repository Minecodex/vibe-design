import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { ChevronDown } from 'lucide-react'

import {
  formatAspectRatioOptionLabelWithDimensions,
  type AspectRatioHintLabels,
  formatResolutionOptionLabel,
} from '../generatorOptionLabels'
import {
  getAllowedImageRatiosForResolution,
  getAllowedImageResolutions,
  getImageCapabilityFromConfig,
  getResolvedImageModelCapability,
  resolveImageModelSelection,
} from '../imageModelConfig'
import { getCanvasItemDimensions } from '../mediaDimensions'
import { handleScrollableWheel } from '../scrollableWheel'
import { GeneratorImageSourcePicker } from './GeneratorImageSourcePicker'
import { GeneratorReferenceStrip } from './GeneratorReferenceStrip'
import { useGeneratorReferenceChips } from './useGeneratorReferenceChips'

type ImageModelOption = {
  value: string
  name: string
  provider: string
  providerName: string
  config?: {
    allowed_aspect_ratios?: string[]
    allowed_aspect_ratios_by_size?: Record<string, string[]>
    allowed_sizes?: string[]
    dimension_table?: Record<string, Record<string, { width?: number | null; height?: number | null }>>
  }
}

type ImageAnchoredImageDraft = {
  sourceImageItemId: string
  sourceImageUrl: string
  prompt: string
  model_name: string
  provider_code: string
  aspect_ratio: string
  resolution: string
  reference_images: string[]
}

interface ImageAnchoredImagePanelProps {
  draft: ImageAnchoredImageDraft
  availableImageModels: ImageModelOption[]
  isDark: boolean
  t: (key: string, fallback?: string) => string
  amountCents: number | null | undefined
  referenceInputRef: RefObject<HTMLInputElement>
  onUpdateDraft: (updates: Partial<ImageAnchoredImageDraft>) => void
  onPreviewImage: (url: string) => void
  onGenerate: () => void
  onPickReferenceFromLibrary: () => void
  onPickReferenceFromReferenceGallery?: () => void
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
        cursor: 'zoom-in',
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

export function ImageAnchoredImagePanel({
  draft,
  availableImageModels,
  isDark,
  t,
  referenceInputRef,
  onUpdateDraft,
  onPreviewImage,
  onGenerate,
  onPickReferenceFromLibrary,
  onPickReferenceFromReferenceGallery = () => {},
}: ImageAnchoredImagePanelProps) {
  const [activeDropdown, setActiveDropdown] = useState<'model' | 'resolution' | 'ratio' | null>(null)

  useEffect(() => {
    const handleClick = () => setActiveDropdown(null)
    window.addEventListener('click', handleClick)
    return () => window.removeEventListener('click', handleClick)
  }, [])

  const supportedImageModels = availableImageModels.filter((model) =>
    getImageCapabilityFromConfig(model.config, model.value).supportsReferenceImages,
  )
  const modelOptions = supportedImageModels.length > 0 ? supportedImageModels : availableImageModels
  const currentModel = modelOptions.find((model) => model.value === draft.model_name) || modelOptions[0]
  const capability = getResolvedImageModelCapability(availableImageModels, draft.model_name, draft.provider_code)
  const totalReferenceCount = draft.reference_images.length + 1
  const referenceUploadDisabled =
    capability.maxReferenceImages > 0 && totalReferenceCount >= capability.maxReferenceImages
  const allowedResolutions = getAllowedImageResolutions(currentModel?.config)
  const allowedRatios = getAllowedImageRatiosForResolution(currentModel?.config, draft.resolution)
  const showRatioSelector = allowedRatios.length > 0
  const ratioHintLabels: AspectRatioHintLabels = {
    square: t('canvas.generator.ratio_hint_square', '鏂瑰舰'),
    landscape: t('canvas.generator.ratio_hint_landscape', '妯悜'),
    portrait: t('canvas.generator.ratio_hint_portrait', '绔栧悜'),
  }
  const standardSuffix = t('canvas.generator.standard_suffix', '鏍囧噯')
  const previewDims = (overrides?: Partial<ImageAnchoredImageDraft>) =>
    getCanvasItemDimensions({
      type: 'image_generator',
      aspect_ratio: overrides?.aspect_ratio || draft.aspect_ratio,
      provider_code: overrides?.provider_code || draft.provider_code,
      resolution: overrides?.resolution || draft.resolution,
      model_name: overrides?.model_name || draft.model_name,
    }, {
      imageModel: overrides?.model_name || draft.model_name,
      imageProvider: overrides?.provider_code || draft.provider_code,
      imageModelConfig: currentModel?.config,
      imageModels: availableImageModels,
    })
  const referenceImagesRef = useRef(draft.reference_images)
  referenceImagesRef.current = draft.reference_images
  const removeReferenceLabel = t('canvas.generator.remove_reference', 'Remove reference')
  const referenceImageLabel = t('canvas.generator.reference_image', 'Reference image')
  const referenceChips = useGeneratorReferenceChips({
    imageUrls: draft.reference_images,
    alt: referenceImageLabel,
    removeLabel: removeReferenceLabel,
  })
  const handleRemoveReference = useCallback((chipId: string) => {
    const index = Number(chipId.split(':', 1)[0])
    if (!Number.isFinite(index)) return
    const referenceImages = referenceImagesRef.current
    onUpdateDraft({
      reference_images: referenceImages.filter((_, imageIndex) => imageIndex !== index),
    })
  }, [onUpdateDraft])

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
      onClick={(event) => {
        event.stopPropagation()
        setActiveDropdown(null)
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--app-foreground)' }}>
          {t('canvas.generator.describe_imagination', '描述你想生成的画面')}
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
            placeholder={t('canvas.generator.prompt_placeholder_image')}
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
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              padding: '12px 16px',
              backgroundColor: 'transparent',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <SourceChip
                imageUrl={draft.sourceImageUrl}
                onPreviewImage={onPreviewImage}
                label={t('canvas.generator.current_image', '当前图片')}
              />
              <GeneratorReferenceStrip
                chips={referenceChips}
                isDark={isDark}
                onPreviewImage={onPreviewImage}
                onRemove={handleRemoveReference}
              />
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              <GeneratorImageSourcePicker
                isDark={isDark}
                label={t('canvas.generator.reference_image', '参考图片')}
                countLabel={`${t('canvas.generator.reference_image', '参考图片')}${capability.maxReferenceImages > 1 ? ` ${totalReferenceCount}/${capability.maxReferenceImages}` : ''}`}
                localLabel={t('canvas.generator.local_image', '本地图片')}
                libraryLabel={t('canvas.generator.source_asset_library', '素材库')}
                referenceLibraryLabel={t('canvas.generator.reference_gallery', '参考图库')}
                active={!referenceUploadDisabled}
                localDisabled={referenceUploadDisabled}
                libraryDisabled={referenceUploadDisabled}
                referenceLibraryDisabled={referenceUploadDisabled}
                onPickLocal={() => referenceInputRef.current?.click()}
                onPickFromLibrary={onPickReferenceFromLibrary}
                onPickFromReferenceLibrary={onPickReferenceFromReferenceGallery}
              />

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
                <span style={{ fontSize: 13, fontWeight: 600 }}>
                  {t('canvas.generator.generate_now', '绔嬪嵆鐢熸垚')}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
            {t('canvas.generator.model_label', '鐢熸垚妯″瀷')}
          </div>
          <div style={{ position: 'relative' }}>
            <div
              onClick={(event) => {
                event.stopPropagation()
                setActiveDropdown(activeDropdown === 'model' ? null : 'model')
              }}
              style={{
                height: 42,
                padding: '0 12px',
                borderRadius: 10,
                border: '1px solid var(--app-border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                fontSize: 14,
                backgroundColor: 'var(--app-control)',
              }}
            >
              <span
                style={{
                  fontWeight: 500,
                  color: 'var(--app-foreground)',
                  display: 'block',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {currentModel?.name || draft.model_name}
              </span>
              <ChevronDown size={18} color="var(--app-foreground-subtle)" />
            </div>
            {activeDropdown === 'model' && (
              <div
                style={{
                  position: 'absolute',
                  bottom: '110%',
                  left: 0,
                  backgroundColor: 'var(--app-glass)',
                  borderRadius: 12,
                  boxShadow: 'var(--app-shadow-panel)',
                  border: '1px solid var(--app-border)',
                  backdropFilter: 'var(--app-blur)',
                  WebkitBackdropFilter: 'var(--app-blur)',
                  padding: 8,
                  width: '100%',
                  minWidth: 200,
                  zIndex: 1001,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                  maxHeight: 200,
                  overflowY: 'auto',
                }}
              >
                {modelOptions.map((model) => (
                  <div
                    key={model.value}
                    onClick={(event) => {
                      event.stopPropagation()
                      const nextCapability = getImageCapabilityFromConfig(model.config, model.value)
                      const nextSelection = resolveImageModelSelection({
                        config: model.config,
                        currentResolution: draft.resolution,
                        currentAspectRatio: draft.aspect_ratio,
                      })
                      const maxExtraReferences = nextCapability.maxReferenceImages > 0
                        ? Math.max(0, nextCapability.maxReferenceImages - 1)
                        : draft.reference_images.length

                      onUpdateDraft({
                        model_name: model.value,
                        provider_code: model.provider,
                        resolution: nextSelection.resolution,
                        aspect_ratio: nextSelection.aspect_ratio,
                        reference_images: draft.reference_images.slice(0, maxExtraReferences),
                      })
                      setActiveDropdown(null)
                    }}
                    style={{
                      padding: '8px 12px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 2,
                      backgroundColor: draft.model_name === model.value ? 'var(--app-control-selected)' : 'transparent',
                    }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.backgroundColor = draft.model_name === model.value
                        ? 'var(--app-control-selected)'
                        : 'var(--app-control-hover)'
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.backgroundColor = draft.model_name === model.value
                        ? 'var(--app-control-selected)'
                        : 'transparent'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--app-foreground)' }}>
                        {model.name}
                      </span>
                      {draft.model_name === model.value && (
                        <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: 'var(--app-primary)' }} />
                      )}
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
            {t('canvas.generator.resolution_label', '清晰度设置')}
          </div>
          <div style={{ position: 'relative' }}>
            <div
              onClick={(event) => {
                event.stopPropagation()
                setActiveDropdown(activeDropdown === 'resolution' ? null : 'resolution')
              }}
              style={{
                height: 42,
                padding: '0 12px',
                borderRadius: 10,
                border: '1px solid var(--app-border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                fontSize: 14,
                backgroundColor: 'var(--app-control)',
              }}
            >
              <span style={{ fontWeight: 500, color: 'var(--app-foreground)' }}>
                {formatResolutionOptionLabel(draft.resolution || allowedResolutions[0] || '1K', standardSuffix)}
              </span>
              <ChevronDown size={18} color="var(--app-foreground-subtle)" />
            </div>
            {activeDropdown === 'resolution' && (
              <div
                style={{
                  position: 'absolute',
                  bottom: '110%',
                  left: 0,
                  backgroundColor: 'var(--app-glass)',
                  borderRadius: 12,
                  boxShadow: 'var(--app-shadow-panel)',
                  border: '1px solid var(--app-border)',
                  padding: 8,
                  width: '100%',
                  minWidth: 100,
                  zIndex: 1001,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
              >
                {allowedResolutions.map((resolution) => (
                  <div
                    key={resolution}
                    onClick={(event) => {
                      event.stopPropagation()
                      onUpdateDraft(resolveImageModelSelection({
                        config: currentModel?.config,
                        currentResolution: draft.resolution,
                        currentAspectRatio: draft.aspect_ratio,
                        nextResolution: resolution,
                      }))
                      setActiveDropdown(null)
                    }}
                    style={{
                      padding: '8px 12px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontSize: 13,
                      color: 'var(--app-foreground)',
                      backgroundColor: (draft.resolution || allowedResolutions[0] || '1K') === resolution
                        ? 'var(--app-control-selected)'
                        : 'transparent',
                    }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.backgroundColor =
                        (draft.resolution || allowedResolutions[0] || '1K') === resolution
                          ? 'var(--app-control-selected)'
                          : 'var(--app-control-hover)'
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.backgroundColor =
                        (draft.resolution || allowedResolutions[0] || '1K') === resolution
                          ? 'var(--app-control-selected)'
                          : 'transparent'
                    }}
                  >
                    {formatResolutionOptionLabel(resolution, standardSuffix)}
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
                style={{
                  height: 42,
                  padding: '0 12px',
                  borderRadius: 10,
                  border: '1px solid var(--app-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  fontSize: 14,
                  backgroundColor: 'var(--app-control)',
                }}
              >
                <span
                  style={{
                    fontWeight: 500,
                    color: 'var(--app-foreground)',
                    display: 'block',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    minWidth: 0,
                    flex: 1,
                  }}
                >
                  {formatAspectRatioOptionLabelWithDimensions(
                    draft.aspect_ratio,
                    ratioHintLabels,
                    previewDims(),
                  )}
                </span>
                <div style={{ flexShrink: 0, marginLeft: 8 }}>
                  <ChevronDown size={18} color="var(--app-foreground-subtle)" />
                </div>
              </div>
              {activeDropdown === 'ratio' && (
                <div
                  onWheel={handleScrollableWheel}
                  style={{
                    position: 'absolute',
                    bottom: 'calc(100% + 8px)',
                    left: 0,
                    backgroundColor: 'var(--app-glass)',
                    borderRadius: 12,
                    boxShadow: 'var(--app-shadow-panel)',
                    border: '1px solid var(--app-border)',
                    padding: 8,
                    width: '100%',
                    minWidth: 120,
                    zIndex: 1001,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                    maxHeight: 200,
                    overflowY: 'auto',
                  }}
                >
                  {allowedRatios.map((ratio) => (
                    <div
                      key={ratio}
                      onClick={(event) => {
                        event.stopPropagation()
                        onUpdateDraft({ aspect_ratio: ratio })
                        setActiveDropdown(null)
                      }}
                      style={{
                        padding: '8px 12px',
                        borderRadius: 8,
                        cursor: 'pointer',
                        fontSize: 13,
                        color: 'var(--app-foreground)',
                        backgroundColor: draft.aspect_ratio === ratio ? 'var(--app-control-selected)' : 'transparent',
                      }}
                      onMouseEnter={(event) => {
                        event.currentTarget.style.backgroundColor = draft.aspect_ratio === ratio
                          ? 'var(--app-control-selected)'
                          : 'var(--app-control-hover)'
                      }}
                      onMouseLeave={(event) => {
                        event.currentTarget.style.backgroundColor = draft.aspect_ratio === ratio
                          ? 'var(--app-control-selected)'
                          : 'transparent'
                      }}
                    >
                      {formatAspectRatioOptionLabelWithDimensions(
                        ratio,
                        ratioHintLabels,
                        previewDims({ aspect_ratio: ratio }),
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


