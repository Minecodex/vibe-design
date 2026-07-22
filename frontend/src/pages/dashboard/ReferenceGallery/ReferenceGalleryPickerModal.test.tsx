import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ReferenceGalleryPickerModal } from './ReferenceGalleryPickerModal'

const listCategoriesMock = vi.fn()
const listStylesMock = vi.fn()
const listClassificationsMock = vi.fn()
const listImagesMock = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => {
      if (key === 'referenceGallery.allCategories') return '全部类目'
      if (key === 'referenceGallery.allStyles') return '全部风格'
      if (key === 'referenceGallery.allClassifications') return '全部分类'
      if (key === 'referenceGallery.selectCategory') return '选择类目'
      if (key === 'referenceGallery.selectStyle') return '选择风格'
      if (key === 'referenceGallery.selectClassification') return '选择分类'
      if (key === 'referenceGallery.picker.title') return '选择参考图'
      if (key === 'referenceGallery.picker.description') return '选择参考图库图片'
      if (key === 'referenceGallery.picker.selected') return `已选 ${options?.count ?? 0} 张`
      if (key === 'common.confirm') return '确认'
      return key
    },
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
  },
}))

vi.mock('@/api/endpoints/referenceGallery', () => ({
  referenceGalleryApi: {
    listCategories: (...args: unknown[]) => listCategoriesMock(...args),
    listStyles: (...args: unknown[]) => listStylesMock(...args),
    listClassifications: (...args: unknown[]) => listClassificationsMock(...args),
    listImages: (...args: unknown[]) => listImagesMock(...args),
  },
}))

describe('ReferenceGalleryPickerModal', () => {
  beforeEach(() => {
    listCategoriesMock.mockReset()
    listStylesMock.mockReset()
    listClassificationsMock.mockReset()
    listImagesMock.mockReset()
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn().mockImplementation(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    )
    vi.stubGlobal(
      'ResizeObserver',
      vi.fn().mockImplementation(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    )
    if (!HTMLElement.prototype.hasPointerCapture) {
      HTMLElement.prototype.hasPointerCapture = () => false
    }
    if (!HTMLElement.prototype.releasePointerCapture) {
      HTMLElement.prototype.releasePointerCapture = () => undefined
    }
    if (!HTMLElement.prototype.scrollIntoView) {
      HTMLElement.prototype.scrollIntoView = () => undefined
    }

    listCategoriesMock.mockResolvedValue({
      data: [
        {
          id: 1,
          name: '衬衫',
          kind: 'category',
          image_count: 1,
          created_at: '2026-06-21T00:00:00',
          updated_at: '2026-06-21T00:00:00',
        },
      ],
    })
    listStylesMock.mockResolvedValue({
      data: [
        {
          id: 2,
          kind: 'style',
          name: '平铺',
          prompt: 'flat lay',
          image_count: 1,
          created_at: '2026-06-21T00:00:00',
          updated_at: '2026-06-21T00:00:00',
        },
      ],
    })
    listClassificationsMock.mockResolvedValue({
      data: [
        {
          id: 3,
          kind: 'classification',
          name: '主图',
          prompt: 'main image',
          image_count: 1,
          created_at: '2026-06-21T00:00:00',
          updated_at: '2026-06-21T00:00:00',
        },
      ],
    })
    listImagesMock.mockResolvedValue({ data: [] })
  })

  test('renders select menus above the canvas modal layer', async () => {
    const user = userEvent.setup()

    render(
      <ReferenceGalleryPickerModal
        open
        onOpenChange={vi.fn()}
        isDark={false}
        onSelect={vi.fn()}
      />,
    )

    await screen.findByRole('dialog')
    await waitFor(() => {
      expect(listCategoriesMock).toHaveBeenCalled()
      expect(listStylesMock).toHaveBeenCalled()
      expect(listClassificationsMock).toHaveBeenCalled()
    })

    await user.click(screen.getAllByRole('combobox')[0])

    const listbox = await screen.findByRole('listbox')
    expect(listbox).toHaveStyle({ zIndex: '2147483647' })
  })

  test('loads images with category, style, and classification filters', async () => {
    const user = userEvent.setup()

    render(
      <ReferenceGalleryPickerModal
        open
        onOpenChange={vi.fn()}
        isDark={false}
        onSelect={vi.fn()}
      />,
    )

    await waitFor(() => expect(listImagesMock).toHaveBeenCalled())

    await user.click(screen.getAllByRole('combobox')[0])
    await user.click(await screen.findByRole('option', { name: '衬衫' }))
    await user.click(screen.getAllByRole('combobox')[1])
    await user.click(await screen.findByRole('option', { name: '平铺' }))
    await user.click(screen.getAllByRole('combobox')[2])
    await user.click(await screen.findByRole('option', { name: '主图' }))

    await waitFor(() => {
      expect(listImagesMock).toHaveBeenLastCalledWith(expect.objectContaining({
        category_id: 1,
        style_id: 2,
        classification_id: 3,
      }))
    })
  })
})
