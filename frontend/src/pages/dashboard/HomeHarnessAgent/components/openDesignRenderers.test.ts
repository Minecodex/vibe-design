import { describe, expect, it } from 'vitest'

import { renderDesignSystemShowcase } from './openDesignShowcaseRenderer'
import { renderDesignSystemTokenPreview } from './openDesignTokenRenderer'

const SAMPLE_DESIGN_SYSTEM = `# Design System Inspired by Airbnb

> Category: E-Commerce & Retail

Travel marketplace. Warm coral accent, photography-driven, rounded UI.

## 1. Visual Theme & Atmosphere

- **Primary background:** \`#FFF8F6\`
- **Surface:** \`#FFFFFF\`
- **Primary text:** \`#222222\`
- **Secondary text:** \`#6B7280\`
- **Brand primary:** \`#FF385C\`
- **Brand secondary:** \`#FFB4C1\`

## 2. Typography

- **Display:** "Airbnb Cereal VF"
- **Body:** "Inter"

## 3. Components

- Buttons use the coral accent sparingly.
- Cards have rounded corners and generous spacing.
`

describe('open design system preview renderers', () => {
  it('renders showcase HTML with open-design-specific sections', () => {
    const html = renderDesignSystemShowcase('airbnb', SAMPLE_DESIGN_SYSTEM)

    expect(html).toContain('Pick the plan that matches the way your team ships')
    expect(html).toContain('Showcase rendered from')
    expect(html).toContain('Tokens that compose')
  })

  it('renders token preview HTML with open-design-specific sections', () => {
    const html = renderDesignSystemTokenPreview('airbnb', SAMPLE_DESIGN_SYSTEM)

    expect(html).toContain('Palette')
    expect(html).toContain('Typography')
    expect(html).toContain('Buttons')
  })
})
