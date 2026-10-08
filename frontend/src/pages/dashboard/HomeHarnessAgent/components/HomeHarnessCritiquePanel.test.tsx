import { createTranslationFixture } from '@/store/testing/translationFixture'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  HomeHarnessCritiquePanel,
  isCritiqueVisible,
  normalizeDesignJuryDimensionKey,
  resolveDesignJuryDimensionLabel,
} from './HomeHarnessCritiquePanel'

const t = createTranslationFixture({
  "home.chat.design_jury.warnings.screenshot_unavailable": "No rendered screenshot was captured; model-led quality review continued.",
  "home.chat.design_jury.warnings.artifact_not_critiqueable": "The current artifact is not an HTML visual deliverable; Design Jury was skipped and publishing is allowed.",
  "home.chat.design_jury.warnings.score_clamped": "A critique score exceeded the configured scale and was clamped.",
  "home.chat.design_jury.dimensions.visual-quality": "Visual quality",
  "home.chat.design_jury.dimension_aliases.clarity-of-value-proposition": "value-proposition-clarity",
  "home.chat.design_jury.dimensions.visual-hierarchy": "Visual hierarchy",
  "home.chat.design_jury.dimensions.cta-clarity": "CTA clarity",
  "home.chat.design_jury.dimensions.value-proposition-clarity": "Value proposition clarity",
  "home.chat.design_jury.dimensions.spacing-and-readability": "Spacing and readability",
  "home.chat.design_jury.dimensions.message-offer-fit": "Message-offer fit",
  "home.chat.design_jury.dimensions.form-interaction-clarity": "Form and interaction clarity",
  "home.chat.design_jury.dimensions.trust-and-proof": "Trust and proof",
  "home.chat.design_jury.dimensions.responsive-adaptation": "Responsive adaptation",
  "home.chat.design_jury.dimensions.typography-readability": "Typography readability",
  "home.chat.design_jury.dimensions.color-and-brand-fit": "Color and brand fit",
  "home.chat.design_jury.dimensions.content-clarity": "Content clarity",
  "home.chat.design_jury.round_completed": "This quality-check round is complete",
  "home.chat.design_jury.round": "Round {{round}}",
  "home.chat.design_jury.round_limit": "Up to {{maxRounds}} rounds",
  "home.chat.design_jury.selected_best_published": "Published round {{round}} as the best version, score {{score}}"
})

describe('HomeHarnessCritiquePanel', () => {
  it('shows the best-version notice and remaining findings below threshold', () => {
    render(
      <HomeHarnessCritiquePanel
        isDark
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'below_threshold',
          round: 3,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: 7.4,
          scores: { critic: 7, brand: 8, a11y: 6, copy: 9 },
          dimensions: [],
          findings: [{ role: 'critic', text: 'Increase hero spacing.' }],
          warnings: [],
          selectedRound: 2,
          selectedScore: 8,
          publishFallback: false,
          reason: null,
        }}
      />,
    )

    expect(screen.getByText('Published round 2 as the best version, score 8')).toBeInTheDocument()
    expect(screen.getByText('- Increase hero spacing.')).toBeInTheDocument()
    expect(screen.getByText('7 / 10')).toBeInTheDocument()
  })

  it('hides the empty armed state until the quality check actually starts', () => {
    const armed = {
      critiqueRunId: 'critique-1',
      status: 'running',
      round: 0,
      maxRounds: 3,
      scoreThreshold: 8,
      scoreScale: 10,
      composite: null,
      scores: {},
      dimensions: [],
      findings: [],
      warnings: [],
      selectedRound: null,
      selectedScore: null,
      publishFallback: false,
      reason: null,
    }

    expect(isCritiqueVisible(null)).toBe(false)
    expect(isCritiqueVisible(armed)).toBe(false)
    expect(isCritiqueVisible({ ...armed, round: 1 })).toBe(true)
    expect(isCritiqueVisible({ ...armed, scores: { critic: 7 } })).toBe(true)
    expect(isCritiqueVisible({ ...armed, status: 'failed' })).toBe(true)

    const { container } = render(
      <HomeHarnessCritiquePanel isDark={false} t={t} critique={armed} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows running and failed quality check states', () => {
    const { rerender } = render(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'running',
          round: 1,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: null,
          scores: { critic: 7 },
          dimensions: [],
          findings: [],
          warnings: [],
          selectedRound: null,
          selectedScore: null,
          publishFallback: false,
          reason: null,
        }}
      />,
    )

    expect(screen.getByText('Quality check is running')).toBeInTheDocument()
    expect(screen.getByText('Round 1')).toBeInTheDocument()
    expect(screen.getByText(/Up to 3 rounds/)).toBeInTheDocument()

    rerender(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'failed',
          round: 0,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: null,
          scores: {},
          dimensions: [],
          findings: [],
          warnings: [],
          selectedRound: null,
          selectedScore: null,
          publishFallback: true,
          reason: 'no_valid_critique_round',
        }}
      />,
    )

    expect(screen.getByText('Published with quality check warnings')).toBeInTheDocument()
  })

  it('does not present max rounds as required remaining work after publishing', () => {
    render(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'shipped',
          round: 2,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: 8.38,
          scores: { critic: 8.4, brand: 8.7, a11y: 8.1, copy: 8.3 },
          dimensions: [],
          findings: [],
          warnings: [],
          selectedRound: 2,
          selectedScore: 8.38,
          publishFallback: false,
          reason: null,
        }}
      />,
    )

    expect(screen.getByText('Round 2')).toBeInTheDocument()
    expect(screen.queryByText(/Up to 3 rounds/)).not.toBeInTheDocument()
    expect(screen.queryByText('Round 2 / 3')).not.toBeInTheDocument()
  })

  it('shows non-blocking critique warnings', () => {
    render(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'running',
          round: 1,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: 7.4,
          scores: { critic: 7 },
          dimensions: [],
          findings: [],
          warnings: [{ code: 'screenshot_unavailable', message: 'No rendered screenshot evidence was provided.' }],
          selectedRound: null,
          selectedScore: null,
          publishFallback: false,
          reason: null,
        }}
      />,
    )

    expect(screen.getByText('Quality check notes')).toBeInTheDocument()
    expect(screen.getByText('- No rendered screenshot was captured; model-led quality review continued.')).toBeInTheDocument()
  })

  it('localizes known dimension names', () => {
    render(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'shipped',
          round: 1,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: 8.4,
          scores: { critic: 8 },
          dimensions: [{ role: 'critic', name: 'visual-quality', score: 8, note: 'Strong hierarchy.' }],
          findings: [],
          warnings: [],
          selectedRound: 1,
          selectedScore: 8.4,
          publishFallback: false,
          reason: null,
        }}
      />,
    )

    expect(screen.getByText('Visual quality')).toBeInTheDocument()
    expect(screen.queryByText('visual-quality')).not.toBeInTheDocument()
  })

  it('normalizes free-form QualityReview dimension names before i18n lookup', () => {
    expect(normalizeDesignJuryDimensionKey(' Visual hierarchy ')).toBe('visual-hierarchy')
    expect(normalizeDesignJuryDimensionKey('CTA clarity')).toBe('cta-clarity')
    expect(normalizeDesignJuryDimensionKey('Tone & personality')).toBe('tone-and-personality')

    expect(resolveDesignJuryDimensionLabel('visual hierarchy', t)).toBe('Visual hierarchy')
    expect(resolveDesignJuryDimensionLabel('CTA clarity', t)).toBe('CTA clarity')
    expect(resolveDesignJuryDimensionLabel('clarity of value proposition', t)).toBe('Value proposition clarity')
    expect(resolveDesignJuryDimensionLabel('spacing and readability', t)).toBe('Spacing and readability')
    expect(resolveDesignJuryDimensionLabel('message-offer fit', t)).toBe('Message-offer fit')
    expect(resolveDesignJuryDimensionLabel('form/interaction clarity', t)).toBe('Form and interaction clarity')
    expect(resolveDesignJuryDimensionLabel('trust and proof', t)).toBe('Trust and proof')
    expect(resolveDesignJuryDimensionLabel('responsive adaptation', t)).toBe('Responsive adaptation')
    expect(resolveDesignJuryDimensionLabel('typography readability', t)).toBe('Typography readability')
    expect(resolveDesignJuryDimensionLabel('color and brand fit', t)).toBe('Color and brand fit')
    expect(resolveDesignJuryDimensionLabel('content clarity', t)).toBe('Content clarity')
    expect(resolveDesignJuryDimensionLabel('unknown dimension', t)).toBe('unknown dimension')
  })

  it('renders round completed as a completed quality-check state', () => {
    render(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'running',
          displayStatus: 'round_completed',
          round: 1,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: 7.4,
          scores: { critic: 7 },
          dimensions: [],
          findings: [],
          warnings: [],
          selectedRound: null,
          selectedScore: null,
          publishFallback: false,
          reason: null,
        }}
      />,
    )

    expect(screen.getByText('This quality-check round is complete')).toBeInTheDocument()
    expect(screen.queryByText('Quality check is running')).not.toBeInTheDocument()
  })

  it('shows artifact skip and scoring warning notes while hiding internal scoring mismatch notes', () => {
    render(
      <HomeHarnessCritiquePanel
        isDark={false}
        t={t}
        critique={{
          critiqueRunId: 'critique-1',
          status: 'failed',
          round: 0,
          maxRounds: 3,
          scoreThreshold: 8,
          scoreScale: 10,
          composite: null,
          scores: {},
          dimensions: [],
          findings: [],
          warnings: [
            { code: 'artifact_not_critiqueable', message: 'Current artifact is not critiqueable.' },
            { code: 'score_clamped', message: 'Score clamped.' },
            { code: 'composite_mismatch', message: 'Composite mismatch.' },
          ],
          selectedRound: null,
          selectedScore: null,
          publishFallback: true,
          reason: 'artifact_not_critiqueable',
        }}
      />,
    )

    expect(screen.getByText('- The current artifact is not an HTML visual deliverable; Design Jury was skipped and publishing is allowed.')).toBeInTheDocument()
    expect(screen.getByText('- A critique score exceeded the configured scale and was clamped.')).toBeInTheDocument()
    expect(screen.queryByText(/Composite mismatch/)).not.toBeInTheDocument()
    expect(screen.queryByText(/backend scoring/)).not.toBeInTheDocument()
  })
})
