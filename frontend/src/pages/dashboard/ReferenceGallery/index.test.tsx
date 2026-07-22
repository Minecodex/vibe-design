import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ReferenceGalleryPage } from './index'

const listCategoriesMock = vi.fn()
const listStylesMock = vi.fn()
const listClassificationsMock = vi.fn()
const listImagesMock = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const labels: Record<string, string> = {
        'referenceGallery.tabs.gallery': '参考图库',
        'referenceGallery.tabs.categories': '类目',
        'referenceGallery.tabs.styles': '图片风格',
        'referenceGallery.tabs.classifications': '图片分类',
        'referenceGallery.allCategories': '全部类目',
        'referenceGallery.allStyles': '全部风格',
        'referenceGallery.allClassifications': '全部分类',
        'referenceGallery.selectCategory': '选择类目',
        'referenceGallery.selectStyle': '选择风格',
        'referenceGallery.selectClassification': '选择分类',
        'referenceGallery.empty': '暂无参考图，请先上传图片',
        'referenceGallery.upload.button': '上传参考图',
        'referenceGallery.taxonomy.empty': '暂无',
        'referenceGallery.category': '类目',
        'referenceGallery.style': '图片风格',
        'referenceGallery.classification': '图片分类',
        'referenceGallery.add': '新增',
        'referenceGallery.edit': '编辑',
        'referenceGallery.delete': '删除',
        'common.loading': '加载中',
      }
      return labels[key] ?? key
    },
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: { user: { id: number; role: string } }) => unknown) =>
    selector({ user: { id: 1, role: 'admin' } }),
}))

vi.mock('@/api/endpoints/referenceGallery', () => ({
  referenceGalleryApi: {
    listCategories: (...args: unknown[]) => listCategoriesMock(...args),
    listStyles: (...args: unknown[]) => listStylesMock(...args),
    listClassifications: (...args: unknown[]) => listClassificationsMock(...args),
    listImages: (...args: unknown[]) => listImagesMock(...args),
    createTaxonomy: vi.fn(),
    deleteTaxonomy: vi.fn(),
    updateTaxonomy: vi.fn(),
    deleteImage: vi.fn(),
    updateImage: vi.fn(),
    uploadImages: vi.fn(),
  },
}))

vi.mock('@/components/ui/CachedImage', () => ({
  CachedImage: (props: { alt?: string }) => <div data-testid="cached-image">{props.alt}</div>,
}))

vi.mock('@/components/project/AssetPreviewModal', () => ({
  AssetPreviewModal: () => <div data-testid="asset-preview" />,
}))

describe('ReferenceGalleryPage', () => {
  beforeEach(() => {
    listCategoriesMock.mockReset()
    listStylesMock.mockReset()
    listClassificationsMock.mockReset()
    listImagesMock.mockReset()
    listCategoriesMock.mockResolvedValue({ data: [{ id: 1, kind: 'category', name: '衬衫', image_count: 0, created_at: '', updated_at: '' }] })
    listStylesMock.mockResolvedValue({ data: [{ id: 2, kind: 'style', name: '平铺', prompt: 'flat', image_count: 0, created_at: '', updated_at: '' }] })
    listClassificationsMock.mockResolvedValue({ data: [{ id: 3, kind: 'classification', name: '主图', prompt: 'main', image_count: 0, created_at: '', updated_at: '' }] })
    listImagesMock.mockResolvedValue({ data: [] })
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn().mockImplementation(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
      })),
    )
    if (!HTMLElement.prototype.scrollTo) {
      HTMLElement.prototype.scrollTo = () => undefined
    }
  })

  test('defaults to gallery tab and loads image filters', async () => {
    render(<ReferenceGalleryPage />)

    await waitFor(() => expect(listImagesMock).toHaveBeenCalled())
    expect(screen.getByRole('tab', { name: '参考图库' })).toHaveAttribute('data-state', 'active')
    expect(screen.getByRole('button', { name: '上传参考图' })).toBeInTheDocument()
  })

  test('renders reference images in an asset-library-like seven column grid', async () => {
    listImagesMock.mockResolvedValue({
      data: [{
        id: 11,
        url: '/ref.png',
        name: '大图/IMG_E9291.JPG',
        category_id: 1,
        category_name: 'Polo衫',
        style_id: 2,
        style_name: '街拍潮流',
        classification_id: 3,
        classification_name: '平铺图',
        created_at: '',
        updated_at: '',
      }],
    })

    render(<ReferenceGalleryPage />)

    expect((await screen.findAllByText('大图/IMG_E9291.JPG')).length).toBeGreaterThan(0)
    expect(screen.getByTestId('reference-gallery-image-grid')).toHaveClass('2xl:grid-cols-7')
    expect(screen.getByText('Polo衫')).toBeInTheDocument()
  })

  test('switches to taxonomy management tabs', async () => {
    const user = userEvent.setup()
    render(<ReferenceGalleryPage />)

    await user.click(screen.getByRole('tab', { name: '图片风格' }))
    expect(screen.getByText('平铺')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新增' })).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('输入图片风格名称')).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: '图片分类' }))
    expect(screen.getByText('主图')).toBeInTheDocument()
  })
})
