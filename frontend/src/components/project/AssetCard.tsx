import { useRef } from 'react'
import { Video, Image as ImageIcon, Clock, Heart } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { AssetRead, getAssetListMediaUrl } from '@/api/endpoints/assets'
import { CachedImage } from '@/components/ui/CachedImage'
import { StatusBadge } from '@/components/common/ui'

interface AssetCardProps {
  asset: AssetRead
  onToggleFavorite: (asset: AssetRead) => void
  onClick: () => void
  activeTab?: 'all' | 'image' | 'video'
  showFavoriteAction?: boolean
}

export function AssetCard({ asset, onToggleFavorite, onClick, activeTab = 'all', showFavoriteAction = true }: AssetCardProps) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const listMediaUrl = getAssetListMediaUrl(asset)

  const handleMouseEnter = () => {
    if (asset.asset_type === 'video' && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay might be blocked by browser even if muted, though usually okay
        console.warn('Video autoplay failed')
      })
    }
  }

  const handleMouseLeave = () => {
    if (asset.asset_type === 'video' && videoRef.current) {
      videoRef.current.pause()
      videoRef.current.currentTime = 0
    }
  }

  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ scale: 1.02, zIndex: 10 }}
      className="group relative aspect-square min-h-[250px] w-full min-w-[250px] cursor-pointer overflow-hidden rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-surface-solid)] shadow-sm transition-all duration-300 hover:z-10 hover:shadow-[var(--app-shadow-panel)]"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
    >
      {asset.asset_type === 'video' ? (
        <video 
          ref={videoRef}
          src={asset.url} 
          className="w-full h-full object-cover" 
          preload="metadata" 
          muted 
          loop 
          playsInline
        />
      ) : (
        <CachedImage src={listMediaUrl} alt="" className="w-full h-full object-cover" />
      )}
      
      {/* Top Left Badge */}
      <div className="absolute top-4 left-4 z-10">
        {asset.origin_kind === 'local_upload' && (
          <StatusBadge variant="default" className="border border-[color-mix(in_srgb,var(--app-border)_55%,transparent)] bg-[color-mix(in_srgb,var(--app-bg)_72%,transparent)] text-[10px] uppercase tracking-widest text-foreground backdrop-blur-md">
            {t('local_upload_badge', '本地上传')}
          </StatusBadge>
        )}
      </div>

      {/* Top Right Type Icon (Visible in 'all' tab) */}
      {activeTab === 'all' && (
        <div className="absolute top-4 right-4 z-20">
          <div className="flex h-8 w-8 items-center justify-center rounded-[var(--app-radius-xs)] border border-[color-mix(in_srgb,var(--app-primary-foreground)_22%,transparent)] bg-[color-mix(in_srgb,var(--app-bg)_34%,transparent)] text-[var(--app-primary-foreground)]/80 backdrop-blur-sm">
            {asset.asset_type === 'video' ? <Video className="w-4 h-4" /> : <ImageIcon className="w-4 h-4" />}
          </div>
        </div>
      )}

      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
      <div className="invisible absolute inset-0 flex flex-col justify-end p-5 group-hover:visible">
        <div className="flex translate-y-2 items-center justify-between text-white transition-transform duration-150 group-hover:translate-y-0">
          <div className="flex items-center gap-2 text-[12px] font-bold text-[var(--app-media-foreground-muted)]">
            <Clock className="w-3.5 h-3.5" />
            {new Date(asset.updated_at || asset.created_at).toLocaleDateString()}
          </div>
          {showFavoriteAction && (
            <button 
              onClick={(e) => { 
                e.stopPropagation(); 
                onToggleFavorite(asset); 
              }}
              className={cn(
                'w-9 h-9 rounded-full flex items-center justify-center backdrop-blur-xl transition-all',
                asset.is_favorite
                  ? 'bg-[var(--app-primary)] shadow-lg shadow-[var(--app-tint-primary-hover)]'
                  : 'bg-[color-mix(in_srgb,var(--app-primary-foreground)_12%,transparent)] hover:bg-[color-mix(in_srgb,var(--app-primary-foreground)_20%,transparent)]'
              )}
            >
              <Heart className={cn('w-4.5 h-4.5', asset.is_favorite ? 'fill-white text-white' : 'text-white')} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  )
}
