import { describe, expect, it } from 'vitest'

import { getModelDisplayName } from './modelDisplayName'

describe('getModelDisplayName', () => {
  it('aliases suffixed Seedream 5.0 model names', () => {
    expect(getModelDisplayName(undefined, 'doubao-seedream-5-0-260128')).toBe('Seedream 5.0')
  })

  it('aliases LingyaAI generation model ids used by usage logs', () => {
    expect(getModelDisplayName(undefined, 'doubao-seedream-4-5-251128')).toBe('Seedream 4.5')
    expect(getModelDisplayName(undefined, 'doubao-seedance-2-0-260128')).toBe('Seedance 2.0')
  })

  it('uses the alias when the provided label is the same raw model token', () => {
    expect(getModelDisplayName('doubao-seedream-5-0-260128', 'doubao-seedream-5-0-260128')).toBe('Seedream 5.0')
  })

  it('keeps a real human label when one is provided', () => {
    expect(getModelDisplayName('Custom Image Model', 'doubao-seedream-5-0-260128')).toBe('Custom Image Model')
  })
})
