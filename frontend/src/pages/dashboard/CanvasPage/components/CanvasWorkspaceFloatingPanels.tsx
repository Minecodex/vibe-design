// @ts-nocheck

import {
  Box,
  Check,
  Copy,
  Crop,
  Eraser,
  Image as ImageIcon,
  Info,
  MoreHorizontal,
  RotateCcw,
  Trash2,
  Type,
  Video,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { getImageUrl } from '@/utils/imageUrl'

import { TextRedrawPanel } from './TextRedrawPanel'
import { canRenameCanvasItem } from '../canvasItemRename'
import { isRetryableFailedGenerationItem } from '../generationFailure'
import { handleScrollableWheel } from '../scrollableWheel'

function ImageDetailCard({
  item,
  data,
  position,
  isDark,
  t,
  showCloseButton,
  onClose,
  onMouseEnter,
  onMouseLeave,
}: any) {
  const [copied, setCopied] = useState(false)
  const generationMeta = data?.generationMeta
  const copyLabel = t('copy', '复制')
  const copiedLabel = t('copied', '已复制')
  const copyPromptLabel = t('canvas.detail.copy_prompt', '复制提示词')

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1200)
    return () => window.clearTimeout(timer)
  }, [copied])

  const handleCopyPrompt = async () => {
    if (!generationMeta?.prompt) return
    try {
      await navigator.clipboard.writeText(generationMeta.prompt)
      setCopied(true)
    } catch (error) {
      console.error('Failed to copy prompt:', error)
    }
  }

  if (!item || !data || !position) {
    return null
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: position.left,
        top: position.top,
        width: position.width,
        minHeight: position.height,
        borderRadius: 16,
        backgroundColor: 'var(--app-glass)',
        border: '1px solid var(--app-border)',
        boxShadow: 'var(--app-shadow-panel)',
        padding: 20,
        zIndex: 2147483551,
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--app-foreground)' }}>
          {t('canvas.toolbar.image_info', '图片信息')}
        </span>
        {showCloseButton && (
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ width: 28, height: 28, borderRadius: 999, border: 'none', background: 'var(--app-control)', color: 'var(--app-foreground-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
          >
            <X size={14} />
          </button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, color: 'var(--app-foreground)', fontSize: 14, userSelect: 'text', WebkitUserSelect: 'text', cursor: 'text' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.creator', '创建人：')}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <Avatar size="sm">
              <AvatarImage src={getImageUrl(data.creatorAvatar) || undefined} alt={data.creatorName} />
              <AvatarFallback>{data.creatorName.slice(0, 1).toUpperCase()}</AvatarFallback>
            </Avatar>
            <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data.creatorName}</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.format', '图片格式：')}</span><span>{data.fileFormat}</span></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.size', '图片大小：')}</span><span>{data.imageSize}</span></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.created_at', '创建时间：')}</span><span>{data.updatedAt}</span></div>
        {generationMeta && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.model', '模型')}</span><span>{generationMeta.model}</span></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.resolution', '分辨率')}</span><span>{generationMeta.resolution}</span></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><span style={{ minWidth: 72, color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.dimensions', '长宽')}</span><span>{generationMeta.dimensions}</span></div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ color: 'var(--app-foreground-muted)' }}>{t('canvas.detail.prompt', '提示词')}</span>
                <button
                  type="button"
                  aria-label={copyPromptLabel}
                  onClick={handleCopyPrompt}
                  style={{ border: 'none', background: 'var(--app-control)', color: 'var(--app-foreground-muted)', borderRadius: 10, padding: '6px 10px', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{copied ? copiedLabel : copyLabel}</span>
                </button>
              </div>
              <div
                className="nowheel"
                onWheel={handleScrollableWheel}
                style={{
                  maxHeight: 72,
                  overflowY: 'auto',
                  padding: '10px 12px',
                  borderRadius: 12,
                  background: 'var(--app-surface-muted)',
                  border: '1px solid var(--app-border)',
                  lineHeight: 1.5,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {generationMeta.prompt}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export function CanvasWorkspaceFloatingPanels(props: any) {
  const {
    imageDetailItem,
    imageDetailData,
    imageDetailPanelPosition,
    isDark,
    t,
    handleCloseImageDetails,
    textRedrawState,
    textRedrawPanelPosition,
    TEXT_REDRAW_PANEL_TOKENS,
    handleChangeTextRedrawSegment,
    handleCancelTextRedraw,
    handleSubmitTextRedraw,
    selectedSingleItem,
    selectedSingleItemRect,
    selectedSingleItemCanvasRect,
    activeTool,
    cropState,
    shouldShowImageToolbar,
    imageAnchoredImageDraft,
    imageAnchoredVideoDraft,
    openImageAnchoredImageDraft,
    openImageAnchoredVideoDraft,
    handleOpenHDUpscale,
    handleOpenCutout,
    handleOpenImageErase,
    handleOpenTextRedraw,
    handleOpenSpatialAngle,
    handleOpenCropPanel,
    handleDeleteCanvasImage,
    handleOpenImageDetails,
    handleRetryFailedGeneration,
    shouldRenderSelectedMeta,
    selectedSingleItemViewportWidth,
    selectedIsImageGroup,
    editingNameId,
    updateItem,
    setEditingNameId,
    selectedIsGenerator,
    formatDimensionLabel,
    selectedSingleItemWidth,
    selectedSingleItemHeight,
    projectedGuides,
    selectionBox,
    isPanning,
  } = props
  const selectedFloatingRect = selectedSingleItemCanvasRect || selectedSingleItemRect
  const canRenameSelectedItem = canRenameCanvasItem(selectedSingleItem)

  return (
    <>
      <ImageDetailCard
        item={imageDetailItem}
        data={imageDetailData}
        position={imageDetailPanelPosition}
        isDark={isDark}
        t={t}
        showCloseButton
        onClose={handleCloseImageDetails}
      />

      {textRedrawState?.status === 'editing' && textRedrawPanelPosition && (
        <div className="nowheel" onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()} onWheel={(e) => { if (e.nativeEvent.cancelable) e.preventDefault(); e.stopPropagation() }} style={{ position: 'absolute', left: textRedrawPanelPosition.left, top: textRedrawPanelPosition.top, width: textRedrawPanelPosition.width, height: textRedrawPanelPosition.height, borderRadius: TEXT_REDRAW_PANEL_TOKENS.panelRadius, backgroundColor: 'var(--app-glass)', border: '1px solid var(--app-border)', boxShadow: 'var(--app-shadow-panel)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)', padding: TEXT_REDRAW_PANEL_TOKENS.panelPadding, zIndex: 2147483550, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <TextRedrawPanel isDark={isDark} title={t('canvas.text_redraw.detect_result', 'Detected text')} segmentLabelPrefix={t('canvas.text_redraw.segment_label', 'Text')} submitLabel={t('canvas.text_redraw.submit', 'Apply redraw')} segments={textRedrawState.segments} isSubmitting={textRedrawState.isSubmitting} onChangeSegment={handleChangeTextRedrawSegment} onCancel={handleCancelTextRedraw} onSubmit={handleSubmitTextRedraw} />
        </div>
      )}

      {!isPanning && selectedSingleItem && selectedFloatingRect && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2147483450, pointerEvents: 'none' }}>
          <div
            id={selectedSingleItem.type === 'group' ? undefined : `canvas-screen-preview-${selectedSingleItem.id}`}
            data-canvas-preview-scale={selectedSingleItemRect && selectedSingleItemCanvasRect ? selectedSingleItemCanvasRect.width / Math.max(1, selectedSingleItemWidth) : 1}
            style={{ position: 'absolute', left: selectedFloatingRect.left + (selectedFloatingRect.width / 2), top: selectedFloatingRect.top - 8, display: 'flex', flexDirection: 'column', gap: 6, transform: 'translate(-50%, -100%)', pointerEvents: 'auto', width: 'max-content', maxWidth: 'calc(100% - 32px)' }}
          >
            {activeTool === 'select' && !cropState && isRetryableFailedGenerationItem(selectedSingleItem) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, alignSelf: 'center', backgroundColor: 'var(--app-glass)', border: '1px solid var(--app-border)', padding: '6px 12px', borderRadius: 12, boxShadow: 'var(--app-shadow-control)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)', whiteSpace: 'nowrap', width: 'fit-content' }}>
                <div onClick={(e) => { e.stopPropagation(); handleRetryFailedGeneration(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}>
                  <RotateCcw size={14} />
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.generator.retry', '重新生成')}</span>
                </div>
              </div>
            )}
            {activeTool === 'select' && !cropState && selectedSingleItem && shouldShowImageToolbar(selectedSingleItem.type) && !(imageAnchoredImageDraft && imageAnchoredImageDraft.sourceImageItemId === selectedSingleItem.id) && !(imageAnchoredVideoDraft && imageAnchoredVideoDraft.sourceImageItemId === selectedSingleItem.id) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, alignSelf: 'center', backgroundColor: 'var(--app-glass)', border: '1px solid var(--app-border)', padding: '6px 12px', borderRadius: 12, boxShadow: 'var(--app-shadow-control)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)', whiteSpace: 'nowrap', width: 'fit-content' }}>
                  <div onClick={(e) => { e.stopPropagation(); openImageAnchoredImageDraft(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}><ImageIcon size={14} /> <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.gen_image', '生成图片')}</span></div>
                  <div style={{ width: 1, height: 20, backgroundColor: 'var(--app-border)', margin: '0 4px' }} />
                  <div onClick={(e) => { e.stopPropagation(); openImageAnchoredVideoDraft(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}><Video size={14} /> <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.gen_video', '生成视频')}</span></div>
                  <div onClick={(e) => { e.stopPropagation(); handleOpenHDUpscale(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}><span style={{ fontWeight: 'bold', fontSize: 13, lineHeight: '14px' }}>HD</span><span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.hd_upscale', '高清')}</span></div>
                  <div onClick={(e) => { e.stopPropagation(); handleOpenCutout(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}><ImageIcon size={14} /> <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.cutout', '抠图')}</span></div>
                  <div onClick={(e) => { e.stopPropagation(); handleOpenImageErase(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}><Eraser size={14} /> <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.erase', '消除笔')}</span></div>
                  <div onClick={(e) => { e.stopPropagation(); handleOpenTextRedraw(selectedSingleItem.id) }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', color: 'var(--app-foreground)' }}><Type size={14} /> <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.redraw_text', '文字重绘')}</span></div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', outline: 'none', color: 'var(--app-foreground)' }} onClick={(e) => { e.stopPropagation() }}>
                        <MoreHorizontal size={14} /> <span style={{ fontSize: 13, fontWeight: 500 }}>{t('canvas.chat.tool_tips.more', 'More')}</span>
                      </div>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent style={{ backgroundColor: 'var(--app-glass)', border: '1px solid var(--app-border)', boxShadow: 'var(--app-shadow-panel)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)', borderRadius: 10, zIndex: 2147483550, minWidth: 140, padding: '6px' }} side="bottom" align="start" sideOffset={10} alignOffset={28} onClick={(e) => e.stopPropagation()}>
                      <DropdownMenuItem onClick={() => handleOpenSpatialAngle(selectedSingleItem.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', minHeight: 32, padding: '0 10px', borderRadius: 6, fontSize: 13 }}><Box size={14} /> <span>{t('canvas.toolbar.spatial_angle', '空间角度')}</span></DropdownMenuItem>
                      <DropdownMenuItem onClick={() => handleOpenCropPanel(selectedSingleItem.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', minHeight: 32, padding: '0 10px', borderRadius: 6, fontSize: 13 }}><Crop size={14} /> <span>{t('canvas.toolbar.crop', '裁剪')}</span></DropdownMenuItem>
                      <DropdownMenuSeparator style={{ backgroundColor: 'var(--app-border)', margin: '4px 0' }} />
                      <DropdownMenuItem onClick={() => handleDeleteCanvasImage(selectedSingleItem.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', color: 'var(--app-danger)', minHeight: 32, padding: '0 10px', borderRadius: 6, fontSize: 13 }}><Trash2 size={14} color="var(--app-danger)" /> <span style={{ color: 'var(--app-danger)' }}>{t('canvas.chat.tool_tips.delete', '删除')}</span></DropdownMenuItem>
                      <DropdownMenuItem onClick={() => handleOpenImageDetails(selectedSingleItem.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', minHeight: 32, padding: '0 10px', borderRadius: 6, fontSize: 13 }}><Info size={14} /> <span>{t('canvas.toolbar.image_info', '图片信息')}</span></DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
            )}
            <div style={{ display: shouldRenderSelectedMeta && selectedSingleItem.type !== 'group' ? 'flex' : 'none', justifyContent: 'space-between', alignItems: 'center', gap: 12, width: shouldRenderSelectedMeta ? selectedSingleItemViewportWidth : '100%', maxWidth: 'calc(100vw - 32px)', alignSelf: 'center', fontSize: 13, color: 'var(--app-foreground-muted)', whiteSpace: 'nowrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500, minWidth: 0 }} onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
                {editingNameId === selectedSingleItem.id && canRenameSelectedItem ? (
                  <input autoFocus value={selectedSingleItem.name || ''} onChange={(e) => updateItem(selectedSingleItem.id, { name: e.target.value })} onBlur={() => setEditingNameId(null)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') setEditingNameId(null) }} style={{ border: 'none', background: 'transparent', fontSize: 13, color: 'var(--app-foreground-muted)', outline: 'none', padding: '0 2px', fontWeight: 500, minWidth: 40 }} />
                ) : (
                  <span onClick={() => { if (canRenameSelectedItem) setEditingNameId(selectedSingleItem.id) }} onMouseDown={(e) => e.stopPropagation()} style={{ cursor: canRenameSelectedItem ? 'text' : 'default', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {selectedIsGenerator ? (selectedIsImageGroup ? t('canvas.generator.image_title') : t('canvas.generator.video_title')) : (selectedSingleItem.name || selectedSingleItem.id)}
                  </span>
                )}
              </div>
              <span style={{ color: 'var(--app-foreground-subtle)', pointerEvents: 'none', flexShrink: 0 }}>{formatDimensionLabel(selectedSingleItemWidth, selectedSingleItemHeight)}</span>
            </div>
          </div>
        </div>
      )}

      {!isPanning && projectedGuides.length > 0 && (
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 2147483400 }}>
          {projectedGuides.map((guide: any) => (
            <div key={`${guide.axis}-${guide.sourceItemId}-${guide.matchedAnchor}-${guide.left}-${guide.top}`} style={{ position: 'absolute', left: guide.left, top: guide.top, width: guide.width, height: guide.height, backgroundColor: 'color-mix(in srgb, var(--app-primary) 70%, transparent)', borderRadius: 999, boxShadow: '0 0 0 1px var(--app-focus-ring)' }} />
          ))}
        </div>
      )}

      {selectionBox && (
        <div style={{ position: 'fixed', left: Math.min(selectionBox.x1, selectionBox.x2), top: Math.min(selectionBox.y1, selectionBox.y2), width: Math.abs(selectionBox.x1 - selectionBox.x2), height: Math.abs(selectionBox.y1 - selectionBox.y2), border: '1px solid var(--app-primary)', backgroundColor: 'color-mix(in srgb, var(--app-primary) 10%, transparent)', zIndex: 2147483600, pointerEvents: 'none' }} />
      )}
    </>
  )
}


