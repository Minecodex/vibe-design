import { describe, expect, it } from 'vitest'

import {
  applyHomeHarnessCritiqueEvent,
  hydrateHomeHarnessCritique,
} from './homeHarnessCritiqueProjection'

describe('homeHarnessCritiqueProjection', () => {
  it('projects critique SSE events', () => {
    const result = applyHomeHarnessCritiqueEvent(null, {
      type: 'critique.below_threshold',
      data: {
        critique_run_id: 'critique-1',
        status: 'below_threshold',
        round: 3,
        max_rounds: 3,
        score_threshold: 8,
        score_scale: 10,
        composite: 7.4,
        scores: { critic: 7, brand: 8, a11y: 6, copy: 9 },
        findings: [{ role: 'critic', text: 'Fix hierarchy' }],
        warnings: [{ code: 'screenshot_unavailable', message: 'No rendered screenshot evidence was provided.' }],
        selected_round: 2,
        selected_score: 3.2,
      },
    })

    expect(result).toMatchObject({
      critiqueRunId: 'critique-1',
      status: 'below_threshold',
      round: 3,
      maxRounds: 3,
      selectedRound: 2,
      selectedScore: 3.2,
    })
    expect(result?.findings[0].text).toBe('Fix hierarchy')
    expect(result?.warnings[0]).toEqual({
      code: 'screenshot_unavailable',
      message: 'No rendered screenshot evidence was provided.',
    })
  })

  it('projects critique started and quality failure states', () => {
    const started = applyHomeHarnessCritiqueEvent(null, {
      type: 'critique.started',
      data: {
        critique_run_id: 'critique-1',
        status: 'running',
        max_rounds: 3,
        score_threshold: 8,
        score_scale: 10,
      },
    })
    expect(started?.status).toBe('running')
    expect(started?.maxRounds).toBe(3)

    const failed = applyHomeHarnessCritiqueEvent(started, {
      type: 'critique.degraded',
      data: {
        status: 'degraded',
        publish_fallback: true,
        reason: 'no_valid_critique_round',
      },
    })

    expect(failed?.status).toBe('degraded')
    expect(failed?.publishFallback).toBe(true)
    expect(failed?.reason).toBe('no_valid_critique_round')
  })

  it('hydrates reconnect state from the conversation detail runtime snapshot', () => {
    const result = hydrateHomeHarnessCritique({
      critique: {
        critique_run_id: 'critique-2',
        status: 'running',
        round: 1,
        max_rounds: 3,
        score_threshold: 8,
        warnings: [{ code: 'screenshot_unavailable', message: 'No rendered screenshot evidence was provided.' }],
      },
    })

    expect(result?.critiqueRunId).toBe('critique-2')
    expect(result?.round).toBe(1)
    expect(result?.status).toBe('running')
    expect(result?.warnings[0].code).toBe('screenshot_unavailable')
  })

  it('projects open-design style warning codes without filtering them out', () => {
    const result = applyHomeHarnessCritiqueEvent(null, {
      type: 'critique.degraded',
      data: {
        critique_run_id: 'critique-3',
        status: 'degraded',
        publish_fallback: true,
        reason: 'artifact_not_critiqueable',
        warnings: [
          { code: 'artifact_not_critiqueable', message: 'Current artifact is not critiqueable.' },
          { code: 'score_clamped', message: 'Score clamped.' },
          { code: 'unknown_role', message: 'Unknown role ignored.' },
          { code: 'composite_mismatch', message: 'Composite mismatch.' },
        ],
      },
    })

    expect(result?.reason).toBe('artifact_not_critiqueable')
    expect(result?.publishFallback).toBe(true)
    expect(result?.warnings.map((warning) => warning.code)).toEqual([
      'artifact_not_critiqueable',
      'score_clamped',
      'unknown_role',
      'composite_mismatch',
    ])
  })
})
