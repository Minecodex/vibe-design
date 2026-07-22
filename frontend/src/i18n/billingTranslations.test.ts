import { describe, expect, it } from 'vitest'

import enUS from './locales/en-US.json'
import zhCN from './locales/zh-CN.json'

describe('billing translations', () => {
  it('uses amount terminology for the usage table cost column', () => {
    expect(zhCN.billing.col_cost).toBe('金额')
    expect(enUS.billing.col_cost).toBe('Amount')
  })

  it('defines a localized blocked status label for billing usage rows', () => {
    expect(zhCN.billing.status_blocked).toBe('已阻塞')
    expect(enUS.billing.status_blocked).toBe('Blocked')
  })
})
