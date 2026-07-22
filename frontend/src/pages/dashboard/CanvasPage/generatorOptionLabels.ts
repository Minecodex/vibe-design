export interface AspectRatioHintLabels {
  square: string
  landscape: string
  portrait: string
}

export function formatDimensionLabel(width: number, height: number): string {
  return `${Math.round(width)} × ${Math.round(height)}`
}

export function formatResolutionOptionLabel(value: string, standardLabel: string): string {
  return value === '1K' ? `${value}（${standardLabel}）` : value
}

function getAspectRatioHintKey(ratio: string): keyof AspectRatioHintLabels | null {
  if (ratio === '1:1') return 'square'
  if (ratio === '16:9' || ratio === '21:9') return 'landscape'
  if (ratio === '9:16') return 'portrait'
  return null
}

export function formatAspectRatioOptionLabel(ratio: string, labels: AspectRatioHintLabels): string {
  const hintKey = getAspectRatioHintKey(ratio)

  if (!hintKey) {
    return ratio
  }

  return `${ratio}（${labels[hintKey]}）`
}

export function formatAspectRatioOptionLabelWithDimensions(
  ratio: string,
  labels: AspectRatioHintLabels,
  dimensions: { width: number; height: number },
): string {
  return `${formatAspectRatioOptionLabel(ratio, labels)} ${formatDimensionLabel(dimensions.width, dimensions.height)}`
}
