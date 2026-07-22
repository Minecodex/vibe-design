export const TEXT_REDRAW_PANEL_TOKENS = {
  panelWidth: 332,
  panelHeight: 520,
  panelGap: 16,
  panelMargin: 32,
  panelRadius: 24,
  panelPadding: 20,
  titleFontSize: 16,
  titlePaddingBottom: 14,
  closeButtonSize: 30,
  scrollGap: 14,
  scrollPaddingTop: 16,
  segmentLabelFontSize: 13,
  inputHeight: 50,
  inputRadius: 14,
  inputFontSize: 14,
  inputPaddingX: 16,
  inputIconOffset: 14,
  submitButtonHeight: 52,
  submitButtonRadius: 18,
  submitButtonFontSize: 15,
  submitButtonIconSize: 16,
  extractingBadgeMinWidth: 112,
  extractingBadgeHeight: 44,
  extractingBadgeRadius: 14,
  extractingBadgeFontSize: 14,
  extractingBadgePaddingX: 16,
  extractingBadgeLetterSpacing: 0.5,
} as const

export function getTextRedrawExtractingBadgeStyle(args: {
  zoom: number
}) {
  const { zoom } = args
  const safeZoom = zoom > 0 ? zoom : 100

  return {
    minWidth: TEXT_REDRAW_PANEL_TOKENS.extractingBadgeMinWidth,
    height: TEXT_REDRAW_PANEL_TOKENS.extractingBadgeHeight,
    borderRadius: TEXT_REDRAW_PANEL_TOKENS.extractingBadgeRadius,
    border: '1px solid var(--app-border)',
    background: 'var(--app-glass)',
    boxShadow: 'var(--app-shadow-panel)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--app-foreground)',
    fontSize: TEXT_REDRAW_PANEL_TOKENS.extractingBadgeFontSize,
    fontWeight: 700,
    letterSpacing: TEXT_REDRAW_PANEL_TOKENS.extractingBadgeLetterSpacing,
    padding: `0 ${TEXT_REDRAW_PANEL_TOKENS.extractingBadgePaddingX}px`,
    transform: `scale(${100 / safeZoom})`,
    transformOrigin: 'center center',
    whiteSpace: 'nowrap',
  } as const
}
