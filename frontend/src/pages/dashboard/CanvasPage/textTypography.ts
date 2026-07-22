import type { CanvasItem } from '@/api/endpoints/projects'

export type TextFontVariant = 'Regular' | 'Medium' | 'SemiBold' | 'Bold' | 'Italic'
export type TextListStyle = 'none' | 'ordered' | 'unordered'
export type TextTransformStyle = 'none' | 'uppercase' | 'lowercase' | 'capitalize'
export type TextWritingMode = 'horizontal' | 'vertical'

export type TextCanvasItem = CanvasItem & {
  type: 'text'
  text: string
  fontFamily: string
  fontVariant: TextFontVariant
  fontSize: number
  fillColor: string
  strokeColor: string
  strokeWidth: number
  textAlign: 'left' | 'center' | 'right'
  lineHeight: number
  letterSpacing: number
  underline: boolean
  strikeThrough: boolean
  listStyle: TextListStyle
  textTransform: TextTransformStyle
  writingMode: TextWritingMode
  width: number
  height: number
}

export type TextFontSource = {
  path: string
  weight: number
  style: 'normal' | 'italic'
}

export type TextFontDefinition = {
  family: string
  label: string
  variants: TextFontVariant[]
  sources: TextFontSource[]
}

export const DEFAULT_TEXT_FONT_FAMILY = 'Instrument Sans'
export const DEFAULT_TEXT_FONT_SIZE = 80
export const DEFAULT_TEXT_VALUE = '输入文字'
export const DEFAULT_TEXT_FILL = '#111111'
export const DEFAULT_TEXT_STROKE = 'transparent'
export const DEFAULT_TEXT_LINE_HEIGHT = 1.2
export const DEFAULT_TEXT_LETTER_SPACING = 0

const FONT_SOURCE_ROOT = '/fonts/canvas-text'

export const textFontRegistry: TextFontDefinition[] = [
  {
    family: 'Instrument Sans',
    label: 'Instrument Sans',
    variants: ['Regular', 'Medium', 'SemiBold', 'Bold', 'Italic'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/instrument-sans-regular.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/instrument-sans-medium.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/instrument-sans-semibold.ttf`, weight: 600, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/instrument-sans-bold.ttf`, weight: 700, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/instrument-sans-italic.ttf`, weight: 400, style: 'italic' },
    ],
  },
  {
    family: 'Cormorant Garamond',
    label: 'Cormorant Garamond',
    variants: ['Regular', 'Medium', 'SemiBold', 'Bold', 'Italic'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/cormorant-garamond-regular.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/cormorant-garamond-medium.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/cormorant-garamond-semibold.ttf`, weight: 600, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/cormorant-garamond-bold.ttf`, weight: 700, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/cormorant-garamond-italic.ttf`, weight: 400, style: 'italic' },
    ],
  },
  {
    family: 'Space Grotesk',
    label: 'Space Grotesk',
    variants: ['Regular', 'Medium', 'Bold'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/space-grotesk-regular.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/space-grotesk-medium.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/space-grotesk-bold.ttf`, weight: 700, style: 'normal' },
    ],
  },
  {
    family: 'Libre Baskerville',
    label: 'Libre Baskerville',
    variants: ['Regular', 'Bold', 'Italic'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/libre-baskerville-regular.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/libre-baskerville-bold.ttf`, weight: 700, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/libre-baskerville-italic.ttf`, weight: 400, style: 'italic' },
    ],
  },
  {
    family: 'Manrope',
    label: 'Manrope',
    variants: ['Regular', 'Medium', 'SemiBold', 'Bold'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/manrope-variable.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/manrope-variable.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/manrope-variable.ttf`, weight: 600, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/manrope-variable.ttf`, weight: 700, style: 'normal' },
    ],
  },
  {
    family: 'Plus Jakarta Sans',
    label: 'Plus Jakarta Sans',
    variants: ['Regular', 'Medium', 'SemiBold', 'Bold', 'Italic'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/plus-jakarta-sans-variable.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/plus-jakarta-sans-variable.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/plus-jakarta-sans-variable.ttf`, weight: 600, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/plus-jakarta-sans-variable.ttf`, weight: 700, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/plus-jakarta-sans-italic-variable.ttf`, weight: 400, style: 'italic' },
    ],
  },
  {
    family: 'DM Sans',
    label: 'DM Sans',
    variants: ['Regular', 'Medium', 'SemiBold', 'Bold', 'Italic'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/dm-sans-variable.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/dm-sans-variable.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/dm-sans-variable.ttf`, weight: 600, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/dm-sans-variable.ttf`, weight: 700, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/dm-sans-italic-variable.ttf`, weight: 400, style: 'italic' },
    ],
  },
  {
    family: 'Playfair Display',
    label: 'Playfair Display',
    variants: ['Regular', 'Medium', 'SemiBold', 'Bold', 'Italic'],
    sources: [
      { path: `${FONT_SOURCE_ROOT}/playfair-display-variable.ttf`, weight: 400, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/playfair-display-variable.ttf`, weight: 500, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/playfair-display-variable.ttf`, weight: 600, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/playfair-display-variable.ttf`, weight: 700, style: 'normal' },
      { path: `${FONT_SOURCE_ROOT}/playfair-display-italic-variable.ttf`, weight: 400, style: 'italic' },
    ],
  },
]

const FONT_VARIANT_STYLE_MAP: Record<TextFontVariant, { fontWeight: number; fontStyle: 'normal' | 'italic' }> = {
  Regular: { fontWeight: 400, fontStyle: 'normal' },
  Medium: { fontWeight: 500, fontStyle: 'normal' },
  SemiBold: { fontWeight: 600, fontStyle: 'normal' },
  Bold: { fontWeight: 700, fontStyle: 'normal' },
  Italic: { fontWeight: 400, fontStyle: 'italic' },
}

export function getTextFontDefinition(fontFamily?: string | null): TextFontDefinition {
  return textFontRegistry.find((font) => font.family === fontFamily) || textFontRegistry[0]
}

export function getSupportedFontVariants(fontFamily?: string | null): TextFontVariant[] {
  return getTextFontDefinition(fontFamily).variants
}

export function getVariantForFontFamily(fontFamily?: string | null, requestedVariant?: string | null): TextFontVariant {
  const fontDefinition = textFontRegistry.find((font) => font.family === fontFamily)
  if (!fontDefinition) return 'Regular'
  const variants = fontDefinition.variants
  return variants.includes((requestedVariant || 'Regular') as TextFontVariant)
    ? (requestedVariant as TextFontVariant)
    : 'Regular'
}

export function getFontVariantCss(fontFamily?: string | null, variant?: string | null) {
  return FONT_VARIANT_STYLE_MAP[getVariantForFontFamily(fontFamily || DEFAULT_TEXT_FONT_FAMILY, variant)]
}

export function applyTextTransform(value: string, transform?: TextTransformStyle) {
  if (transform === 'uppercase') return value.toUpperCase()
  if (transform === 'lowercase') return value.toLowerCase()
  if (transform === 'capitalize') {
    return value.replace(/\b(\p{L})/gu, (match) => match.toUpperCase())
  }
  return value
}

export function formatTextContentForDisplay(item: Pick<TextCanvasItem, 'text' | 'listStyle' | 'textTransform'>) {
  const rawLines = (item.text || '').split('\n')
  return rawLines.map((line, index) => {
    const transformed = applyTextTransform(line, item.textTransform)
    if (item.listStyle === 'ordered') return `${index + 1}. ${transformed}`
    if (item.listStyle === 'unordered') return `• ${transformed}`
    return transformed
  })
}

export function estimateTextCanvasSize(args: {
  text?: string
  fontSize?: number
  lineHeight?: number
  writingMode?: TextWritingMode
  width?: number
  height?: number
}) {
  const text = args.text || DEFAULT_TEXT_VALUE
  const fontSize = Math.max(args.fontSize || DEFAULT_TEXT_FONT_SIZE, 12)
  const lineHeight = Math.max(args.lineHeight || DEFAULT_TEXT_LINE_HEIGHT, 0.8)
  const lines = text.split('\n')
  const longestLine = lines.reduce((max, line) => Math.max(max, line.length), 0) || 1

  if (args.writingMode === 'vertical') {
    return {
      width: Math.max(args.width || 0, Math.round(lines.length * fontSize * lineHeight) + 32),
      height: Math.max(args.height || 0, Math.round(longestLine * fontSize * 1.05) + 32),
    }
  }

  const estimatedWidth = Math.round(Math.max(longestLine * fontSize * 0.62, fontSize * 2)) + 40
  const estimatedHeight = Math.round(lines.length * fontSize * lineHeight) + 32

  return {
    width: Math.max(args.width || 0, estimatedWidth),
    height: Math.max(args.height || 0, estimatedHeight),
  }
}

export function normalizeTextCanvasItem(item: CanvasItem): TextCanvasItem {
  const fontFamily = item.fontFamily || DEFAULT_TEXT_FONT_FAMILY
  const fontVariant = getVariantForFontFamily(fontFamily, item.fontVariant)
  const fontSize = item.fontSize || DEFAULT_TEXT_FONT_SIZE
  const writingMode = item.writingMode || 'horizontal'
  const estimatedSize = estimateTextCanvasSize({
    text: item.text,
    fontSize,
    lineHeight: item.lineHeight,
    writingMode,
    width: item.width,
    height: item.height,
  })

  return {
    ...item,
    type: 'text',
    url: item.url || '',
    text: item.text || DEFAULT_TEXT_VALUE,
    fontFamily,
    fontVariant,
    fontSize,
    fillColor: item.fillColor || DEFAULT_TEXT_FILL,
    strokeColor: item.strokeColor || DEFAULT_TEXT_STROKE,
    strokeWidth: item.strokeWidth ?? 0,
    textAlign: item.textAlign || 'left',
    lineHeight: item.lineHeight || DEFAULT_TEXT_LINE_HEIGHT,
    letterSpacing: item.letterSpacing ?? DEFAULT_TEXT_LETTER_SPACING,
    underline: Boolean(item.underline),
    strikeThrough: Boolean(item.strikeThrough),
    listStyle: item.listStyle || 'none',
    textTransform: item.textTransform || 'none',
    writingMode,
    width: item.width || estimatedSize.width,
    height: item.height || estimatedSize.height,
  }
}

export function createTextCanvasItem(args: {
  id: string
  x: number
  y: number
  zIndex?: number
  text?: string
}): TextCanvasItem {
  return normalizeTextCanvasItem({
    id: args.id,
    type: 'text',
    url: '',
    x: args.x,
    y: args.y,
    z_index: args.zIndex || 1,
    text: args.text || DEFAULT_TEXT_VALUE,
    fontFamily: DEFAULT_TEXT_FONT_FAMILY,
    fontVariant: 'Regular',
    fontSize: DEFAULT_TEXT_FONT_SIZE,
    fillColor: DEFAULT_TEXT_FILL,
    strokeColor: DEFAULT_TEXT_STROKE,
    strokeWidth: 0,
    textAlign: 'left',
    lineHeight: DEFAULT_TEXT_LINE_HEIGHT,
    letterSpacing: DEFAULT_TEXT_LETTER_SPACING,
    underline: false,
    strikeThrough: false,
    listStyle: 'none',
    textTransform: 'none',
    writingMode: 'horizontal',
  })
}

export function getTextItemVariantStyle(item: Pick<TextCanvasItem, 'fontFamily' | 'fontVariant'>) {
  const normalizedVariant = getVariantForFontFamily(item.fontFamily, item.fontVariant)
  return FONT_VARIANT_STYLE_MAP[normalizedVariant]
}
