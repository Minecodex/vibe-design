import { describe, expect, it } from 'vitest'

import { buildInteractionDisplayLabel } from './homeInteractionSummary'
import { localizeInteractionSchema } from './homeInteractionI18n'

describe('homeInteractionSummary', () => {
  it('summarizes quick brief answers in schema order', () => {
    const label = buildInteractionDisplayLabel(
      'quick_brief',
      {
        title: 'Quick brief',
        fields: [
          { id: 'audience', label: 'Audience', type: 'text', required: true },
          {
            id: 'platform',
            label: 'Platform',
            type: 'select',
            required: true,
            options: [{ label: 'Marketing site', value: 'marketing_site' }],
          },
          { id: 'output', label: 'Output', type: 'text', required: true },
        ],
      },
      {
        output: 'Landing page',
        audience: 'Founders',
        platform: 'marketing_site',
      },
      'en-US',
    )

    expect(label).toBe('Founders / Marketing site / Landing page')
  })

  it('uses other labels when quick brief answers contain custom structured selections', () => {
    const label = buildInteractionDisplayLabel(
      'quick_brief',
      {
        title: 'Quick brief',
        fields: [
          {
            id: 'content_focus',
            label: 'Content focus',
            type: 'radio',
            required: true,
            options: [{ label: 'Trend analysis', value: 'trend_analysis' }],
          },
          {
            id: 'speaker_notes',
            label: 'Speaker notes',
            type: 'checkbox',
            required: true,
            options: [{ label: 'Add notes', value: 'add_notes' }],
          },
        ],
      },
      {
        content_focus: {
          type: 'other',
          value: 'Expert interview',
          label: 'Other: Expert interview',
        },
        speaker_notes: [
          'add_notes',
          {
            type: 'other',
            value: 'Transitions',
            label: 'Other: Transitions',
          },
        ],
      },
      'en-US',
    )

    expect(label).toBe('Other: Expert interview / Add notes / Other: Transitions')
  })
})

describe('homeInteractionI18n', () => {
  it('preserves backend quick brief copy when schema already provides english text', () => {
    const localized = localizeInteractionSchema(
      'quick_brief',
      {
        title: 'Quick brief for launch',
        description: 'Choose only the missing constraints.',
        submit_label: 'Lock brief',
        fields: [
          { id: 'output', label: 'Deliverable', type: 'text', required: true, placeholder: 'Landing page' },
          {
            id: 'platform',
            label: 'Platform',
            type: 'select',
            required: true,
            options: [{ label: '线下演讲', value: 'live_presentation' }],
          },
        ],
      },
      'en-US',
    )

    expect(localized?.title).toBe('Quick brief for launch')
    expect(localized?.description).toBe('Choose only the missing constraints.')
    expect(localized?.submit_label).toBe('Lock brief')
    expect(localized?.fields?.[0]?.label).toBe('Deliverable')
    expect(localized?.fields?.[0]?.placeholder).toBe('Landing page')
    expect(localized?.fields?.[1]?.options?.[0]?.label).toBe('Live presentation')
  })
})
