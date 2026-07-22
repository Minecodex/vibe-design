import { describe, expect, it } from 'vitest'

import { getLocalizedSubagentPurpose } from './subagentDisplayLabels'

const t = (key: string, options?: { defaultValue?: string }) => (
  key === 'subagent.purposeLabels.qualityReview'
    ? '质量评审'
    : options?.defaultValue ?? key
)

describe('getLocalizedSubagentPurpose', () => {
  it('localizes QualityReview purposes from the subagent type', () => {
    expect(getLocalizedSubagentPurpose(t as any, 'Quality review', 'QualityReview')).toBe('质量评审')
  })

  it('localizes the known Quality review purpose when type metadata is unavailable', () => {
    expect(getLocalizedSubagentPurpose(t as any, 'Quality review')).toBe('质量评审')
  })

  it('keeps custom subagent purposes unchanged', () => {
    expect(getLocalizedSubagentPurpose(t as any, 'Visual QA Slides 1-5')).toBe('Visual QA Slides 1-5')
  })
})
