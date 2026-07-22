import { describe, expect, it } from 'vitest'

import enUS from '@/i18n/locales/en-US.json'
import zhCN from '@/i18n/locales/zh-CN.json'
import { buildCanvasChatSkills } from './chatSkills'

describe('chat skills i18n', () => {
  it('provides readable English locale strings for chat skills', () => {
    expect(enUS.canvas.chat.skills.logo).toBe('Logo Design')
    expect(enUS.canvas.chat.skills.brand_strategy_architect).toBe('Brand Strategy')
    expect(enUS.canvas.chat.skills['menswear-ecommerce-hero']).toBe('Menswear E-commerce Images')
    expect(enUS.canvas.chat.skills['vi-design-guide']).toBe('VI Design Guide')
  })

  it('provides readable Chinese locale strings for chat skills', () => {
    expect(zhCN.canvas.chat.skills.logo).toBe('Logo 设计')
    expect(zhCN.canvas.chat.skills.brand_strategy_architect).toBe('品牌策划方案')
    expect(zhCN.canvas.chat.skills['menswear-ecommerce-hero']).toBe('男装电商图')
    expect(zhCN.canvas.chat.skills['vi-design-guide']).toBe('VI 设计指南')
  })

  it('normalizes the legacy product hero skill id before rendering labels', () => {
    const skills = buildCanvasChatSkills(
      {
        hiddenToolCalls: [],
        canvasExplicitSkillIds: ['product-hero'],
        canvasSkills: [
          {
            id: 'product-hero',
            name: 'product-hero',
            name_en: 'E-commerce Product Images',
            name_zh: '电商商品图',
            description: '',
            icon: 'image',
            color: '',
            triggers: [],
            mode: 'image',
            default_for: [],
            preview_type: 'none',
            capabilities: { canvas_explicit: true },
          } as any,
        ],
      },
      'zh-CN',
      (key, fallback) => (key === 'canvas.chat.skills.menswear-ecommerce-hero' ? '男装电商图' : fallback),
    )

    expect(skills).toHaveLength(1)
    expect(skills[0].id).toBe('menswear-ecommerce-hero')
    expect(skills[0].name).toBe('男装电商图')
  })
})
