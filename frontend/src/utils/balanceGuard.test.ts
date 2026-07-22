import { describe, expect, it } from 'vitest'

import {
  isBalanceRequiredForMultimodalProvider,
  isBalanceRequiredForProvider,
} from './balanceGuard'

describe('balanceGuard provider checks', () => {
  it('does not require balance for Ollama providers', () => {
    expect(isBalanceRequiredForProvider('ollama')).toBe(false)
    expect(isBalanceRequiredForProvider(' OLLAMA ')).toBe(false)
  })

  it('keeps the multimodal provider helper aligned with the generic provider helper', () => {
    expect(isBalanceRequiredForMultimodalProvider('ollama')).toBe(false)
    expect(isBalanceRequiredForMultimodalProvider('builtin')).toBe(true)
  })
})
