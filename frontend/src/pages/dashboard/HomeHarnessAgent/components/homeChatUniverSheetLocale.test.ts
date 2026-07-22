import { describe, expect, it } from 'vitest'
import { LocaleType } from '@univerjs/presets'

import { resolveSheetUniverLocale } from './homeChatUniverSheetLocale'

describe('resolveSheetUniverLocale', () => {
  it('includes the sheet locale bundle for sheet editors', () => {
    const config = resolveSheetUniverLocale('zh-CN')

    expect(config.locale).toBe(LocaleType.ZH_CN)
    expect(config.locales[LocaleType.ZH_CN]).toHaveProperty('sheets')
  })
})
