import { describe, expect, test } from 'vitest'

import { shouldWrapGeneratorFooterActions } from './generatorFooterLayout'

describe('shouldWrapGeneratorFooterActions', () => {
  test('returns false when reference image count is below the wrap threshold', () => {
    expect(shouldWrapGeneratorFooterActions(11)).toBe(false)
  })

  test('returns true when reference image count reaches the wrap threshold', () => {
    expect(shouldWrapGeneratorFooterActions(12)).toBe(true)
  })
})
