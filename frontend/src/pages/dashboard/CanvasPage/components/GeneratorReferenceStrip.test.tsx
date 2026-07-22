import { createRef, useState, type MutableRefObject } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { GeneratorReferenceStrip, useGeneratorReferenceChips } from './GeneratorReferenceStrip'

describe('GeneratorReferenceStrip', () => {
  test('reuses generated chip objects when image urls are unchanged by content', () => {
    const chipsRef = createRef<unknown[]>() as MutableRefObject<unknown[] | null>
    chipsRef.current = null

    function Harness() {
      const [dragX, setDragX] = useState(0)
      const chips = useGeneratorReferenceChips({
        imageUrls: [
          'https://example.com/ref-1.png',
          'https://example.com/ref-2.png',
        ],
        alt: 'Reference image',
        removeLabel: 'Remove reference',
      })
      const sameAsPrevious = chipsRef.current === chips
      chipsRef.current = chips

      return (
        <div>
          <button type="button" onClick={() => setDragX((value) => value + 1)}>
            drag {dragX}
          </button>
          <span>{sameAsPrevious ? 'same' : 'new'}</span>
        </div>
      )
    }

    render(<Harness />)
    expect(screen.getByText('new')).toBeInTheDocument()

    fireEvent.click(screen.getByText('drag 0'))

    expect(screen.getByText('same')).toBeInTheDocument()
  })

  test('creates new chip objects when image urls change', () => {
    const chipsRef = createRef<unknown[]>() as MutableRefObject<unknown[] | null>
    chipsRef.current = null

    function Harness() {
      const [imageUrls, setImageUrls] = useState(['https://example.com/ref-1.png'])
      const chips = useGeneratorReferenceChips({
        imageUrls,
        alt: 'Reference image',
        removeLabel: 'Remove reference',
      })
      const sameAsPrevious = chipsRef.current === chips
      chipsRef.current = chips

      return (
        <div>
          <button
            type="button"
            onClick={() => setImageUrls((current) => [
              ...current,
              'https://example.com/ref-2.png',
            ])}
          >
            add
          </button>
          <span>{sameAsPrevious ? 'same' : 'new'}</span>
          <span>{chips.length}</span>
        </div>
      )
    }

    render(<Harness />)
    expect(screen.getByText('new')).toBeInTheDocument()

    fireEvent.click(screen.getByText('add'))

    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('new')).toBeInTheDocument()
  })

  test('previews and removes chips by id', () => {
    const onPreviewImage = vi.fn()
    const onRemove = vi.fn()

    render(
      <GeneratorReferenceStrip
        chips={[{
          id: '0:https://example.com/ref-1.png',
          imageUrl: 'https://example.com/ref-1.png',
          alt: 'Reference image',
          removeLabel: 'Remove reference',
        }]}
        isDark={false}
        onPreviewImage={onPreviewImage}
        onRemove={onRemove}
      />,
    )

    fireEvent.click(screen.getByAltText('Reference image'))
    expect(onPreviewImage).toHaveBeenCalledWith('https://example.com/ref-1.png')

    fireEvent.click(screen.getByRole('button', { name: 'Remove reference' }))
    expect(onRemove).toHaveBeenCalledWith('0:https://example.com/ref-1.png')
  })
})
