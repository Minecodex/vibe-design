import { describe, expect, it } from 'vitest'

import { getLocalizedAppName } from '@/config/brand'

import enUS from './locales/en-US.json'
import zhCN from './locales/zh-CN.json'

describe('brand translations', () => {
  it('uses locale-specific product names in user-facing copy', () => {
    expect(zhCN.login.title).toBe('像素重组')
    expect(enUS.login.title).toBe('Pixel Reorganization')

    expect(zhCN.register.subtitle).toBe('创建您的像素重组账户')
    expect(enUS.register.subtitle).toBe('Create your Pixel Reorganization account')

    expect(zhCN.homepage.showcase_title).toBe('用像素重组设计')
    expect(enUS.homepage.showcase_title).toBe('Design with Pixel Reorganization')

    expect(zhCN.canvas.chat.try_skills).toBe('试试这些像素重组 Skills')
    expect(enUS.canvas.chat.try_skills).toBe('Try these Pixel Reorganization Skills')
  })

  it('localizes organization helper copy for English UI', () => {
    expect(enUS.organization.description).toBe('View and update user account status and profile details')
  })

  it('selects localized app names from runtime config', () => {
    const brand = {
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
    }

    expect(getLocalizedAppName('zh-CN', brand)).toBe('像素重组')
    expect(getLocalizedAppName('en-US', brand)).toBe('Pixel Reorganization')
  })
})
