import { describe, expect, it } from 'vitest'

import enUS from './locales/en-US.json'
import zhCN from './locales/zh-CN.json'

describe('home harness plan approval placeholder translations', () => {
  it('defines localized copy for the locked composer placeholder', () => {
    expect(zhCN.canvas.chat.plan.locked_composer_placeholder).toBe('请先确认下方卡片中的计划，或告诉我需要调整的内容。')
    expect(enUS.canvas.chat.plan.locked_composer_placeholder).toBe('Please confirm or refine the plan in the card below.')
  })
})
