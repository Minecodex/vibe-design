import type { TFunction } from 'i18next'

import type { ToolItem } from './types'

export interface CanvasToolDefinitions {
  tools: ToolItem[]
  selectTools: Array<ToolItem & { shortcut?: string }>
  addTools: ToolItem[]
}

export function getCanvasToolDefinitions(t: TFunction, _isDark: boolean): CanvasToolDefinitions {
  const tools: ToolItem[] = [
    {
      key: 'select',
      label: t('canvas.tools.select'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5.5 4.5l14 6.5-6.5 2.5L10 20.5z" />
        </svg>
      ),
    },
    {
      key: 'add',
      label: t('canvas.tools.add'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="4" width="16" height="16" rx="3" />
          <path d="M12 9v6" />
          <path d="M9 12h6" />
        </svg>
      ),
    },
    {
      key: 'image_gen',
      label: t('canvas.tools.image_gen'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="6" width="14" height="14" rx="2" />
          <path d="M3 15l4-4 4 4" />
          <path d="M9 13l3-3 5 5" />
          <path d="M21 5.5l-2.5-.5-.5-2.5-.5 2.5-2.5.5 2.5.5.5 2.5.5-2.5z" />
        </svg>
      ),
    },
    {
      key: 'video_gen',
      label: t('canvas.tools.video_gen'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="6" width="14" height="14" rx="2" />
          <polygon points="8 10 13 13 8 16" />
          <path d="M21 5.5l-2.5-.5-.5-2.5-.5 2.5-2.5.5 2.5.5.5 2.5.5-2.5z" />
        </svg>
      ),
    },
    {
      key: 'text',
      label: t('canvas.tools.text', '文字'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 5h12" />
          <path d="M12 5v14" />
          <path d="M8 19h8" />
        </svg>
      ),
    },
    {
      key: 'brush',
      label: t('canvas.tools.brush', '鐢荤瑪'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 20h4l10-10-4-4L4 16v4z" />
          <path d="M13 7l4 4" />
        </svg>
      ),
    },
  ]

  const selectTools = [
    {
      key: 'select',
      label: t('canvas.tools.select'),
      shortcut: 'V',
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5.5 4.5l14 6.5-6.5 2.5L10 20.5z" />
        </svg>
      ),
    },
    {
      key: 'hand',
      label: t('canvas.tools.hand'),
      shortcut: 'H',
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 11V6a2 2 0 0 0-4 0v4" />
          <path d="M14 11V4a2 2 0 0 0-4 0v6" />
          <path d="M10 11V5a2 2 0 0 0-4 0v8" />
          <path d="M6 13v-1a2 2 0 0 0-4 0v6a8 8 0 0 0 8 8h2a8 8 0 0 0 8-8v-5a2 2 0 0 0-4 0" />
        </svg>
      ),
    },
    {
      key: 'mark',
      label: t('canvas.tools.mark'),
      shortcut: 'M',
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" />
          <circle cx="12" cy="10" r="3" />
        </svg>
      ),
    },
    {
      key: 'brush',
      label: t('canvas.tools.brush', '鐢荤瑪'),
      shortcut: 'P',
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 20h4l10-10-4-4L4 16v4z" />
          <path d="M13 7l4 4" />
        </svg>
      ),
    },
  ]

  const addTools = [
    {
      key: 'upload_image',
      label: t('canvas.tools.upload_image'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
          <rect x="13" y="13" width="10" height="10" fill="var(--app-glass)" stroke="none" />
          <path d="M16 22v-6" />
          <path d="M14 18l2-2 2 2" />
        </svg>
      ),
    },
    {
      key: 'upload_video',
      label: t('canvas.tools.upload_video'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <polygon points="9 8 15 12 9 16 9 8" />
          <rect x="13" y="13" width="10" height="10" fill="var(--app-glass)" stroke="none" />
          <path d="M16 22v-6" />
          <path d="M14 18l2-2 2 2" />
        </svg>
      ),
    },
    {
      key: 'asset_library',
      label: t('canvas.tools.asset_library', 'Asset Library'),
      svgPath: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
        </svg>
      ),
    },
  ]

  return {
    tools,
    selectTools,
    addTools,
  }
}
