import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip'

describe('Tooltip', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  test('renders tooltip content above the chat sidebar layer', async () => {
    const user = userEvent.setup()

    render(
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button">Hover me</button>
          </TooltipTrigger>
          <TooltipContent>Tooltip content</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    )

    await user.hover(screen.getByRole('button', { name: 'Hover me' }))

    const tooltip = await screen.findByText((content, element) =>
      content === 'Tooltip content' && element?.getAttribute('data-slot') === 'tooltip-content',
    )
    expect(tooltip).toHaveClass('z-[2147483647]')
  })
})
