
import type { HarnessDesignSystemRead } from '@/api/endpoints/agent'

const DESIGN_SYSTEM_FALLBACK_PALETTE = ['#F8FAFC', '#E2E8F0', '#94A3B8', '#0F172A']

export function getDesignSystemPalette(
  designSystem: Pick<HarnessDesignSystemRead, 'palette'> | null | undefined,
): string[] {
  const palette = (designSystem?.palette || [])
    .map((color) => String(color || '').trim())
    .filter((color) => /^#[0-9a-fA-F]{6}$/.test(color))
  return (palette.length > 0 ? palette : DESIGN_SYSTEM_FALLBACK_PALETTE).slice(0, 4)
}

export function getDesignSystemDisplayTitle(
  designSystem: Pick<HarnessDesignSystemRead, 'title'> | null | undefined,
): string {
  return String(designSystem?.title || '').replace(/^Design System Inspired by\s+/i, '').trim()
}

export function getDesignSystemDisplayDescription(
  designSystem: Pick<HarnessDesignSystemRead, 'description' | 'category'> | null | undefined,
): string {
  const category = String(designSystem?.category || '').trim()
  if (category) {
    return category
  }
  return String(designSystem?.description || '')
    .replace(/^Category:\s*/i, '')
    .trim()
}

export function disableOpenDesignPreviewNavigation(html: string): string {
  const disabledHtml = html.replace(/\s+href=(["'])/gi, ' data-disabled-href=$1')
  const guardStyle = `
    <style>
      a, button, [role="button"] {
        pointer-events: none !important;
        cursor: default !important;
      }
    </style>
  `
  if (disabledHtml.includes('</head>')) {
    return disabledHtml.replace('</head>', `${guardStyle}</head>`)
  }
  return `${guardStyle}${disabledHtml}`
}


