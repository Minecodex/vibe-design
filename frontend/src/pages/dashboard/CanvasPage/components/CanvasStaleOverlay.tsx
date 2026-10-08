import type { TFunction } from 'i18next'

export function CanvasStaleOverlay({
  isDark,
  isRefreshingCanvas,
  onRefreshCanvas,
  t,
}: {
  isDark: boolean
  isRefreshingCanvas: boolean
  onRefreshCanvas: () => void | Promise<void>
  t: TFunction
}) {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 2147483647,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: isDark ? 'rgba(10, 13, 18, 0.58)' : 'rgba(248, 250, 252, 0.64)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        pointerEvents: 'auto',
      }}
    >
      <div
        style={{
          width: 'min(420px, calc(100% - 48px))',
          borderRadius: 8,
          border: `1px solid ${isDark ? 'rgba(255,255,255,0.14)' : 'rgba(15,23,42,0.12)'}`,
          background: isDark ? 'rgba(24, 27, 33, 0.88)' : 'rgba(255,255,255,0.92)',
          boxShadow: isDark ? '0 18px 48px rgba(0,0,0,0.34)' : '0 18px 48px rgba(15,23,42,0.14)',
          padding: 20,
          color: isDark ? 'rgba(255,255,255,0.92)' : 'rgba(15,23,42,0.92)',
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: 15, lineHeight: 1.6, marginBottom: 16 }}>
          {t(
            'canvas.stale_overlay.description',
            '此画布已在其他窗口更新。请刷新画布以加载最新版本。',
          )}
        </div>
        <button
          type="button"
          onClick={onRefreshCanvas}
          disabled={isRefreshingCanvas}
          style={{
            height: 36,
            padding: '0 16px',
            borderRadius: 8,
            border: '1px solid transparent',
            background: isDark ? 'rgba(255,255,255,0.92)' : 'rgba(17,24,39,0.92)',
            color: isDark ? 'rgba(17,24,39,0.96)' : '#fff',
            fontSize: 14,
            fontWeight: 500,
            cursor: isRefreshingCanvas ? 'default' : 'pointer',
            opacity: isRefreshingCanvas ? 0.72 : 1,
          }}
        >
          {isRefreshingCanvas
            ? t('canvas.stale_overlay.refreshing', '正在刷新')
            : t('canvas.stale_overlay.refresh', '刷新画布')}
        </button>
      </div>
    </div>
  )
}
