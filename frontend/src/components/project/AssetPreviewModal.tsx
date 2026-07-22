import { useState, useEffect, useRef, useCallback } from 'react'
import { X, ChevronLeft, ChevronRight, Download, Info, Cpu, Image as ImageIcon, User } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { AssetRead } from '@/api/endpoints/assets'
import { getImageUrl } from '@/utils/imageUrl'
import { AssetPreviewThumbnailStrip } from './AssetPreviewThumbnailStrip'

interface AssetPreviewModalProps {
  assets: AssetRead[]
  initialIndex: number
  onClose: () => void
  canDownload?: boolean
}

export function AssetPreviewModal({ assets, initialIndex, onClose, canDownload = true }: AssetPreviewModalProps) {
  const { t } = useTranslation()
  const [currentIndex, setCurrentIndex] = useState(initialIndex)
  const [imageScale, setImageScale] = useState(1)
  const [imageOffset, setImageOffset] = useState({ x: 0, y: 0 })
  const [metadata, setMetadata] = useState<{ resolution?: string; size?: string; format?: string }>({})
  const videoRef = useRef<HTMLVideoElement>(null)
  const dragStateRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null)
  const currentAsset = assets[currentIndex]
  const canGoPrev = currentIndex > 0
  const canGoNext = currentIndex < assets.length - 1

  const clampScale = (value: number) => Math.min(4, Math.max(1, value))

  useEffect(() => {
    if (currentAsset.asset_type === 'video' && videoRef.current) {
      const playPromise = videoRef.current.play()
      if (playPromise !== undefined) {
        playPromise.catch(error => {
          console.log('Autoplay prevented or interrupted:', error)
        })
      }
    }
  }, [currentIndex, currentAsset.asset_type])

  useEffect(() => {
    setImageScale(1)
    setImageOffset({ x: 0, y: 0 })
  }, [currentAsset.id])

  useEffect(() => {
    setMetadata({})

    const format = currentAsset.url.split('.').pop()?.toUpperCase() || 'UNKNOWN'
    setMetadata(prev => ({ ...prev, format }))

    fetch(currentAsset.url, { method: 'HEAD' })
      .then(res => {
        const size = res.headers.get('content-length')
        if (size) {
          const mb = (parseInt(size) / (1024 * 1024)).toFixed(1)
          setMetadata(prev => ({ ...prev, size: `${mb} MB` }))
        } else {
          setMetadata(prev => ({ ...prev, size: 'Unknown' }))
        }
      })
      .catch(() => {
        setMetadata(prev => ({ ...prev, size: 'Unknown' }))
      })
  }, [currentAsset.url])

  const handleMediaLoad = (e: React.SyntheticEvent<HTMLImageElement | HTMLVideoElement>) => {
    if (currentAsset.asset_type === 'image') {
      const img = e.target as HTMLImageElement
      setMetadata(prev => ({ ...prev, resolution: `${img.naturalWidth} x ${img.naturalHeight} px` }))
    } else {
      const video = e.target as HTMLVideoElement
      setMetadata(prev => ({ ...prev, resolution: `${video.videoWidth} x ${video.videoHeight} px` }))
    }
  }

  const handleDownload = async () => {
    try {
      const response = await fetch(currentAsset.url)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      const urlPath = currentAsset.url.split('?')[0]
      const extension = urlPath.split('.').pop()?.toLowerCase() || (currentAsset.asset_type === 'video' ? 'mp4' : 'png')
      link.download = `asset-${currentAsset.id}.${extension}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Download failed:', error)
      window.open(currentAsset.url, '_blank')
    }
  }

  const handlePrev = useCallback(() => {
    setCurrentIndex(prev => Math.max(0, prev - 1))
  }, [])

  const handleNext = useCallback(() => {
    setCurrentIndex(prev => Math.min(assets.length - 1, prev + 1))
  }, [assets.length])

  const handleImageWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (currentAsset.asset_type !== 'image') {
      return
    }

    e.preventDefault()
    const zoomDelta = e.deltaY < 0 ? 0.2 : -0.2
    setImageScale(prev => {
      const nextScale = clampScale(Number((prev + zoomDelta).toFixed(2)))
      if (nextScale === 1) {
        setImageOffset({ x: 0, y: 0 })
      }
      return nextScale
    })
  }

  const handleImagePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (currentAsset.asset_type !== 'image' || imageScale <= 1) {
      return
    }

    const startX = Number(e.clientX ?? 0)
    const startY = Number(e.clientY ?? 0)

    dragStateRef.current = {
      pointerId: e.pointerId,
      startX,
      startY,
      originX: imageOffset.x,
      originY: imageOffset.y,
    }
    if (typeof e.currentTarget.setPointerCapture === 'function') {
      e.currentTarget.setPointerCapture(e.pointerId)
    }
  }

  const handleImagePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current
    if (!dragState || dragState.pointerId !== e.pointerId) {
      return
    }

    const clientX = Number(e.clientX ?? 0)
    const clientY = Number(e.clientY ?? 0)
    const deltaX = clientX - dragState.startX
    const deltaY = clientY - dragState.startY
    setImageOffset({
      x: dragState.originX + deltaX,
      y: dragState.originY + deltaY,
    })
  }

  const handleImagePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragStateRef.current?.pointerId === e.pointerId) {
      dragStateRef.current = null
      if (typeof e.currentTarget.releasePointerCapture === 'function') {
        e.currentTarget.releasePointerCapture(e.pointerId)
      }
    }
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        handlePrev()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        handleNext()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleNext, handlePrev, onClose])

  const getAvatarUrl = (url?: string | null) => {
    if (!url) return null
    return getImageUrl(url) ?? null
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-[var(--app-media-overlay)] p-4 backdrop-blur-xl md:p-12"
      >
        <button
          onClick={onClose}
          className="absolute right-8 top-8 z-[110] flex h-12 w-12 items-center justify-center rounded-full border border-[var(--app-media-border)] bg-[var(--app-media-control)] text-white backdrop-blur-md transition-all hover:bg-[var(--app-media-control-hover)]"
        >
          <X className="w-6 h-6" />
        </button>

        <div className="relative w-full h-full flex flex-col md:flex-row">
          <div className="flex-1 relative flex items-center justify-center min-h-0 px-12 md:px-24">
            <button
              onClick={handlePrev}
              disabled={!canGoPrev}
              data-testid="asset-preview-prev"
              className={cn(
                'absolute left-4 top-1/2 z-10 flex h-14 w-14 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--app-media-border)] bg-[var(--app-media-control)] text-white backdrop-blur-md transition-all hover:bg-[var(--app-media-control-hover)] md:left-8 group',
                !canGoPrev && 'cursor-not-allowed text-[var(--app-media-foreground-subtle)] hover:bg-[var(--app-media-control)]',
              )}
            >
              <ChevronLeft className="w-8 h-8 group-hover:scale-110 transition-transform" />
            </button>

            <button
              onClick={handleNext}
              disabled={!canGoNext}
              data-testid="asset-preview-next"
              className={cn(
                'absolute right-4 top-1/2 z-10 flex h-14 w-14 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--app-media-border)] bg-[var(--app-media-control)] text-white backdrop-blur-md transition-all hover:bg-[var(--app-media-control-hover)] md:right-8 group',
                !canGoNext && 'cursor-not-allowed text-[var(--app-media-foreground-subtle)] hover:bg-[var(--app-media-control)]',
              )}
            >
              <ChevronRight className="w-8 h-8 group-hover:scale-110 transition-transform" />
            </button>

            <AnimatePresence mode="wait">
              <motion.div
                key={currentAsset.id}
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: -20 }}
                transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                className="relative max-h-full max-w-full overflow-hidden rounded-2xl border border-[var(--app-media-border)] bg-[var(--app-media-scrim)] shadow-2xl"
              >
                {currentAsset.asset_type === 'video' ? (
                  <video
                    ref={videoRef}
                    src={currentAsset.url}
                    className="max-h-[70vh] w-auto object-contain"
                    controls
                    autoPlay
                    muted
                    playsInline
                    onLoadedMetadata={handleMediaLoad}
                  />
                ) : (
                  <div
                    className={cn(
                      'max-h-[70vh] max-w-full overflow-hidden',
                      imageScale > 1 ? 'cursor-grab active:cursor-grabbing' : 'cursor-zoom-in'
                    )}
                    onWheel={handleImageWheel}
                    onPointerDown={handleImagePointerDown}
                    onPointerMove={handleImagePointerMove}
                    onPointerUp={handleImagePointerUp}
                    onPointerCancel={handleImagePointerUp}
                    data-testid="asset-preview-image-stage"
                    style={{ touchAction: imageScale > 1 ? 'none' : 'auto' }}
                  >
                    <img
                      src={currentAsset.url}
                      alt=""
                      className="max-h-[70vh] w-auto object-contain origin-center transition-transform duration-150 ease-out select-none"
                      onLoad={handleMediaLoad}
                      style={{ transform: `translate(${imageOffset.x}px, ${imageOffset.y}px) scale(${imageScale})` }}
                      data-testid="asset-preview-image"
                      draggable={false}
                    />
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          <div className="flex w-full flex-col gap-8 overflow-y-auto border-l border-[var(--app-border)] bg-[var(--app-glass)] p-8 text-foreground shadow-2xl backdrop-blur-3xl md:w-96">
            {canDownload && (
              <div className="flex gap-4">
                <button
                  onClick={handleDownload}
                  className="flex flex-1 items-center justify-center gap-2 rounded-[var(--app-radius-sm)] bg-[var(--app-primary)] py-3 font-bold text-[var(--app-primary-foreground)] shadow-[var(--app-shadow-control)] transition-all hover:bg-[var(--app-primary-hover)]"
                >
                  <Download className="w-4 h-4" />
                  {t('projectDetails.download', { defaultValue: '下载' })}
                </button>
              </div>
            )}

            <div className="flex flex-col gap-4">
              <h5 className="text-[10px] uppercase tracking-widest text-[var(--app-foreground-subtle)] font-bold">{t('projectDetails.uploader', { defaultValue: '素材信息' })}</h5>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-800 ring-2 ring-orange-500/20">
                  {currentAsset.adder_avatar ? (
                    <img src={getAvatarUrl(currentAsset.adder_avatar)!} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <User className="w-6 h-6 text-[var(--app-foreground-subtle)]" />
                    </div>
                  )}
                </div>
                <div className="flex flex-col">
                  <span className="font-bold text-lg">{currentAsset.adder_nickname || 'Unknown Artist'}</span>
                  <span className="text-xs text-[var(--app-foreground-subtle)]">{t('projectDetails.memberRole', { defaultValue: '资深视觉艺术家' })}</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-6">
              <h5 className="text-[10px] uppercase tracking-widest text-[var(--app-foreground-subtle)] font-bold">{t('projectDetails.information', { defaultValue: 'INFORMATION' })}</h5>

              <div className="grid gap-4">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-[var(--app-foreground-subtle)]">{t('projectDetails.createdAt', { defaultValue: '创建时间' })}</span>
                  <span className="font-medium">{new Date(currentAsset.updated_at || currentAsset.created_at).toLocaleDateString()}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-[var(--app-foreground-subtle)]">{t('projectDetails.sourceProject', { defaultValue: '所属项目' })}</span>
                  <span className="font-medium truncate max-w-[120px]">{currentAsset.project_name || '-'}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-[var(--app-foreground-subtle)]">{t('projectDetails.type', { defaultValue: '类型' })}</span>
                  <span className="font-medium">{currentAsset.asset_type === 'video' ? 'Video' : 'Image'}</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <h5 className="text-[10px] uppercase tracking-widest text-[var(--app-foreground-subtle)] font-bold">{t('projectDetails.technicalSpecs', { defaultValue: 'TECHNICAL SPECS' })}</h5>

              <div className="grid gap-3">
                <div className="flex items-center gap-4 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4">
                  <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center text-orange-500">
                    <ImageIcon className="w-5 h-5" />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-sm font-bold">{metadata.resolution || 'Scanning...'}</span>
                    <span className="text-[10px] text-[var(--app-foreground-subtle)] uppercase tracking-wider">{t('projectDetails.resolution', { defaultValue: '分辨率' })}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4">
                  <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-500">
                    <Cpu className="w-5 h-5" />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-sm font-bold">{metadata.format || '...'}</span>
                    <span className="text-[10px] text-[var(--app-foreground-subtle)] uppercase tracking-wider">{t('projectDetails.format', { defaultValue: '格式' })}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4">
                  <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-500">
                    <Info className="w-5 h-5" />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-sm font-bold">{metadata.size || 'Calculating...'}</span>
                    <span className="text-[10px] text-[var(--app-foreground-subtle)] uppercase tracking-wider">{t('projectDetails.fileSize', { defaultValue: '文件大小' })}</span>
                  </div>
                </div>
              </div>
            </div>

            {currentAsset.analysis_content ? (
              <div className="flex flex-col gap-4">
                <h5 className="text-[10px] uppercase tracking-widest text-[var(--app-foreground-subtle)] font-bold">
                  {t('projectDetails.imageAnalysis', { defaultValue: '图片分析内容' })}
                </h5>
                <div className="max-h-72 overflow-y-auto rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4 text-sm leading-relaxed text-muted-foreground">
                  {currentAsset.analysis_content}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <AssetPreviewThumbnailStrip
          assets={assets}
          currentIndex={currentIndex}
          onSelect={setCurrentIndex}
        />
      </motion.div>
    </AnimatePresence>
  )
}
