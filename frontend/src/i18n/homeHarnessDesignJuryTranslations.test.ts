import { describe, expect, it } from 'vitest'

import enUS from './locales/en-US.json'
import zhCN from './locales/zh-CN.json'

describe('home harness Design Jury translations', () => {
  it('defines Design Jury copy under the home chat namespace used by the renderer', () => {
    expect(zhCN.home.chat.design_jury.title).toBe('设计评审')
    expect(zhCN.home.chat.design_jury.running).toBe('正在进行质量检查')
    expect(zhCN.home.chat.design_jury.selected_best_published).toBe('已发布第 {{round}} 轮最佳版本，评分 {{score}}')
    expect(zhCN.home.chat.design_jury.roles.critic).toBe('视觉')
    expect(zhCN.home.chat.design_jury.dimensions['visual-quality']).toBe('视觉质量')
    expect(zhCN.home.chat.design_jury.warnings.screenshot_unavailable).toBe('未获得渲染截图，已基于模型质量检查继续。')

    expect(enUS.home.chat.design_jury.title).toBe('Design Jury')
    expect(enUS.home.chat.design_jury.dimensions['visual-quality']).toBe('Visual quality')
  })
})
