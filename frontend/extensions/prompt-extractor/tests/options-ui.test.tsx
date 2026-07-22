import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { OptionsApp } from '../src/options'

describe('prompt extractor options page', () => {
  it('renders a branded card layout similar to the main site login', () => {
    render(<OptionsApp />)

    expect(screen.getByRole('heading', { name: /提取插件|Prompt Extractor/ })).toBeTruthy()
    expect(screen.getAllByText(/提取插件|Prompt Extractor/).length).toBeGreaterThan(1)
    expect(screen.getByText(/网页登录提示词提取|Web prompt extraction/)).toBeTruthy()
    expect(screen.getByLabelText(/服务地址|Server URL/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /登录|Sign in/ })).toBeTruthy()
    expect(screen.getByTestId('options-shell').style.minHeight).toBe('100vh')
    expect(screen.getByTestId('options-card').style.borderRadius).toBe('32px')
  })

  it('shows the restored session state in a success-toned status pill', async () => {
    render(<OptionsApp initialSessionState="saved" />)

    const status = await screen.findByTestId('options-status')
    expect(status.textContent).toMatch(/已保存登录状态|Session restored/)
    expect(status.style.border).toContain('solid')
  })
})
