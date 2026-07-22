import { render, screen } from '@testing-library/react'
import type { TFunction } from 'i18next'
import { describe, expect, it, vi } from 'vitest'

import { CanvasWorkspaceBottomBar } from './CanvasWorkspaceBottomBar'

const translations: Record<string, string> = {
  'canvas.prompt_extractor.entry': '提取插件',
}

const testT = ((key: string, fallback?: string) => translations[key] || fallback || key) as unknown as TFunction

describe('CanvasWorkspaceBottomBar', () => {
  it('keeps the zoom percentage visible when translations are unavailable', () => {
    render(
      <CanvasWorkspaceBottomBar
        isDark={false}
        isLayerPanelOpen={false}
        setIsLayerPanelOpen={vi.fn()}
        zoomOut={vi.fn()}
        zoom={125}
        zoomIn={vi.fn()}
      />,
    )

    expect(screen.getByText('125%')).toBeInTheDocument()
  })

  it('does not render the prompt extractor entry in the bottom workspace toolbar', () => {
    render(
      <CanvasWorkspaceBottomBar
        isDark={false}
        isLayerPanelOpen={false}
        setIsLayerPanelOpen={vi.fn()}
        zoomOut={vi.fn()}
        zoom={125}
        zoomIn={vi.fn()}
        t={testT}
      />,
    )

    expect(screen.queryByRole('button', { name: '提取插件' })).not.toBeInTheDocument()
  })
})
