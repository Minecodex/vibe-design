import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { HomeChatWorkspacePreviewRail } from './HomeChatWorkspacePreviewRail'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key === 'common.download' ? 'Download' : key,
  }),
}))

describe('HomeChatWorkspacePreviewRail', () => {
  it('renders icon-only external open choices after download', () => {
    const onOpenExternal = vi.fn()

    render(
      <HomeChatWorkspacePreviewRail
        title="budget.xlsx"
        isDark={false}
        testId="preview-rail"
        onClose={vi.fn()}
        onDownload={vi.fn()}
        externalOpenSuites={['office', 'wps']}
        onOpenExternal={onOpenExternal}
      >
        <div>Preview</div>
      </HomeChatWorkspacePreviewRail>,
    )

    const downloadButton = screen.getByRole('button', { name: 'Download' })
    const externalButton = screen.getByRole('button', { name: 'home.chat.open_external' })
    const officeButton = screen.getByRole('button', { name: 'home.chat.open_external_office' })
    const wpsButton = screen.getByRole('button', { name: 'home.chat.open_external_wps' })
    const toolbarButtons = screen.getAllByRole('button')

    expect(toolbarButtons.indexOf(externalButton)).toBeGreaterThan(toolbarButtons.indexOf(downloadButton))
    expect(officeButton).toHaveTextContent('')
    expect(wpsButton).toHaveTextContent('')

    fireEvent.click(wpsButton)

    expect(onOpenExternal).toHaveBeenCalledWith('wps')
  })

  it('renders runtime meta summary when provided', () => {
    render(
      <HomeChatWorkspacePreviewRail
        title="index.html"
        isDark={false}
        testId="preview-rail"
        onClose={vi.fn()}
        onDownload={vi.fn()}
        metaSummary={<div data-testid="runtime-meta">template_driven_deck · index.html</div>}
      >
        <div>Preview</div>
      </HomeChatWorkspacePreviewRail>,
    )

    expect(screen.getByTestId('runtime-meta')).toHaveTextContent('template_driven_deck · index.html')
  })
})
