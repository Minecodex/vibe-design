export const GENERATOR_FOOTER_WRAP_THRESHOLD = 12

export function shouldWrapGeneratorFooterActions(referenceImageCount: number): boolean {
  return referenceImageCount >= GENERATOR_FOOTER_WRAP_THRESHOLD
}
