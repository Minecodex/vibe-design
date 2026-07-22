import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'

import { CachedImage, resetCachedImageStateForTests } from './CachedImage'

describe('CachedImage', () => {
  afterEach(() => {
    resetCachedImageStateForTests()
  })

  test('reuses loaded state immediately after an image is unmounted and mounted again', () => {
    const firstRender = render(
      <CachedImage
        src="https://example.com/asset__list_320.webp?v=1"
        alt="asset"
      />,
    )

    const firstImage = screen.getByRole('img', { name: 'asset' })
    expect(firstImage).toHaveAttribute('data-loaded', 'false')

    fireEvent.load(firstImage)
    expect(firstImage).toHaveAttribute('data-loaded', 'true')

    firstRender.unmount()

    render(
      <CachedImage
        src="https://example.com/asset__list_320.webp?v=1"
        alt="asset"
      />,
    )

    expect(screen.getByRole('img', { name: 'asset' })).toHaveAttribute('data-loaded', 'true')
  })
})
