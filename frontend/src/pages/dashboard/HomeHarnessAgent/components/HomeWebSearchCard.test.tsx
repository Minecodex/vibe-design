import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { HomeWebSearchCard } from './HomeWebSearchCard'

vi.mock('./useHarnessMediaSource', () => ({
  useHarnessMediaSource: (_conversationId: string | number | null | undefined, sourceUrl: string | null | undefined) => sourceUrl,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? '',
  }),
}))

describe('HomeWebSearchCard', () => {
  it('opens image results in a preview dialog instead of navigating away', async () => {
    const user = userEvent.setup()

    const { container } = render(
      <HomeWebSearchCard
        isDark={false}
        conversationId="conv-1"
        payload={{
          result: {
            searchType: 'image',
            query: 'cat',
            results: [
              {
                title: 'Cat photo',
                local_image_path: 'http://localhost:8000/test-cat.jpg',
                source_url: 'https://example.com/cat',
              },
            ],
          },
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: /联网图片搜索/i }))
    const sourceLinks = screen.getAllByRole('link', { name: /数据来源|data source/i })
    expect(sourceLinks).toHaveLength(1)
    expect(sourceLinks[0]).toHaveAttribute('href', 'https://example.com/cat')
    await user.click(screen.getByAltText('Cat photo'))

    const previewImages = await screen.findAllByAltText('Cat photo')
    expect(previewImages).toHaveLength(2)
    expect(previewImages[1]).toHaveAttribute('src', 'http://localhost:8000/test-cat.jpg')
    expect(container.querySelector('a[href="https://example.com/cat"]')).toBeTruthy()
  })

  it('renders a data source link for text results', async () => {
    const user = userEvent.setup()

    render(
      <HomeWebSearchCard
        isDark={false}
        conversationId="conv-1"
        payload={{
          result: {
            searchType: 'text',
            query: 'cat facts',
            results: [
              {
                title: 'Cat facts',
                snippet: 'Cats sleep a lot.',
                url: 'https://example.com/cat-facts',
              },
            ],
          },
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: /联网网页搜索/i }))

    const sourceLink = screen.getByRole('link', { name: /数据来源|data source/i })
    expect(sourceLink).toHaveAttribute('href', 'https://example.com/cat-facts')
    expect(screen.queryByRole('link', { name: /打开链接|open link/i })).not.toBeInTheDocument()
  })

  it('uses the displayable image count in the image search subtitle', () => {
    render(
      <HomeWebSearchCard
        isDark={false}
        conversationId="conv-1"
        payload={{
          result: {
            searchType: 'image',
            query: 'kant portrait',
            message: "图片搜索 'kant portrait' 返回了 5 条结果",
            results: [
              { title: 'Kant', local_image_path: 'http://localhost:8000/kant.jpg' },
              { title: 'Kant engraving', local_image_path: 'http://localhost:8000/kant-2.jpg' },
            ],
          },
        }}
      />,
    )

    expect(screen.getByText("图片搜索 'kant portrait' 返回了 2 条结果")).toBeInTheDocument()
    expect(screen.queryByText("图片搜索 'kant portrait' 返回了 5 条结果")).not.toBeInTheDocument()
  })
})
