export type CanvasPerfSnapshot = {
  timestamp: number
  renderer: 'dom' | 'webgl'
  visibleItems: number
  webglItems: number
  overlayItems: number
  domImages: number
  textureCount: number
  loadingTextures: number
}

declare global {
  interface Window {
    __canvasPerfSnapshots?: CanvasPerfSnapshot[]
  }
}

export function recordCanvasPerfSnapshot(snapshot: Omit<CanvasPerfSnapshot, 'timestamp'>) {
  if (import.meta.env.DEV !== true) return
  if (typeof window === 'undefined') return
  const list = window.__canvasPerfSnapshots ?? []
  list.push({
    ...snapshot,
    timestamp: performance.now(),
  })
  if (list.length > 120) {
    list.splice(0, list.length - 120)
  }
  window.__canvasPerfSnapshots = list
}
