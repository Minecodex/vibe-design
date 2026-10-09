import { createTranslationFixture } from '@/store/testing/translationFixture'
import { describe, expect, it } from 'vitest'

import { getLocalizedSubagentPurpose } from './subagentDisplayLabels'

const t = createTranslationFixture({"subagent.purposeLabels.qualityReview":"质量评审"})

describe('getLocalizedSubagentPurpose', () => {
  it('localizes QualityReview purposes from the subagent type', () => {
    expect(getLocalizedSubagentPurpose(t, 'Quality review', 'QualityReview')).toBe('质量评审')
  })

  it('localizes the known Quality review purpose when type metadata is unavailable', () => {
    expect(getLocalizedSubagentPurpose(t, 'Quality review')).toBe('质量评审')
  })

  it('keeps custom subagent purposes unchanged', () => {
    expect(getLocalizedSubagentPurpose(t, 'Visual QA Slides 1-5')).toBe('Visual QA Slides 1-5')
  })
})
