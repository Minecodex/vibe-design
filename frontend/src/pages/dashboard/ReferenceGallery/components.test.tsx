import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { ReferenceImageRead, ReferenceTaxonomyRead } from '@/api/endpoints/referenceGallery'

import { imageLabels, TaxonomyManager, UploadReferenceDialog } from './components'

const createTaxonomyMock = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number; type?: string }) => {
      const labels: Record<string, string> = {
        'referenceGallery.category': '类目',
        'referenceGallery.style': '图片风格',
        'referenceGallery.classification': '图片分类',
        'referenceGallery.selectCategory': '选择类目',
        'referenceGallery.selectStyle': '选择风格',
        'referenceGallery.selectClassification': '选择分类',
        'referenceGallery.noStyle': '不选择风格',
        'referenceGallery.noClassification': '不选择分类',
        'referenceGallery.upload.title': '上传参考图',
        'referenceGallery.upload.description': '上传说明',
        'referenceGallery.upload.images': '选择图片',
        'referenceGallery.upload.folder': '选择文件夹',
        'referenceGallery.upload.empty': '尚未选择图片',
        'referenceGallery.upload.submit': '上传',
        'referenceGallery.upload.uploading': '上传中...',
        'referenceGallery.reset': '重置',
        'referenceGallery.add': '新增',
        'referenceGallery.edit': '编辑',
        'referenceGallery.delete': '删除',
        'referenceGallery.taxonomy.namePlaceholder': `输入${options?.type ?? ''}名称`,
        'referenceGallery.taxonomy.promptPlaceholder': '输入提示词',
        'referenceGallery.taxonomy.created': '已新增',
        'referenceGallery.taxonomy.imageCount': `${options?.count ?? 0} 张图片`,
        'referenceGallery.taxonomy.empty': `暂无${options?.type ?? ''}`,
        'referenceGallery.taxonomy.createTitle': `新增${options?.type ?? ''}`,
        'referenceGallery.taxonomy.editTitle': `编辑${options?.type ?? ''}`,
        'common.cancel': '取消',
        'common.save': '保存',
      }
      if (key === 'referenceGallery.upload.selected') return `已选择 ${options?.count ?? 0} 张图片`
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

vi.mock('@/api/endpoints/referenceGallery', () => ({
  referenceGalleryApi: {
    createTaxonomy: (...args: unknown[]) => createTaxonomyMock(...args),
    deleteTaxonomy: vi.fn(),
    updateTaxonomy: vi.fn(),
  },
}))

const category: ReferenceTaxonomyRead = {
  id: 1,
  kind: 'category',
  name: '衬衫',
  prompt: null,
  image_count: 0,
  created_at: '2026-06-21T00:00:00',
  updated_at: '2026-06-21T00:00:00',
}
const style: ReferenceTaxonomyRead = {
  id: 2,
  kind: 'style',
  name: '平铺',
  prompt: 'flat lay',
  image_count: 0,
  created_at: '2026-06-21T00:00:00',
  updated_at: '2026-06-21T00:00:00',
}
const classification: ReferenceTaxonomyRead = {
  id: 3,
  kind: 'classification',
  name: '主图',
  prompt: 'main image',
  image_count: 0,
  created_at: '2026-06-21T00:00:00',
  updated_at: '2026-06-21T00:00:00',
}

describe('ReferenceGallery components', () => {
  beforeEach(() => {
    createTaxonomyMock.mockReset()
    createTaxonomyMock.mockResolvedValue({ data: { id: 9 } })
    if (!HTMLElement.prototype.hasPointerCapture) {
      HTMLElement.prototype.hasPointerCapture = () => false
    }
    if (!HTMLElement.prototype.releasePointerCapture) {
      HTMLElement.prototype.releasePointerCapture = () => undefined
    }
    if (!HTMLElement.prototype.scrollIntoView) {
      HTMLElement.prototype.scrollIntoView = () => undefined
    }
  })

  test('upload dialog only requires category and files before submit', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <UploadReferenceDialog
        open
        categories={[category]}
        styles={[style]}
        classifications={[classification]}
        pendingFiles={[new File(['x'], 'ref.png', { type: 'image/png' })]}
        submitting={false}
        onOpenChange={vi.fn()}
        onFilesChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    const submit = screen.getByRole('button', { name: '上传' })
    expect(submit).toBeDisabled()

    await user.click(screen.getAllByRole('combobox')[0])
    await user.click(await screen.findByRole('option', { name: '衬衫' }))
    expect(submit).toBeEnabled()

    await user.click(submit)
    expect(onSubmit).toHaveBeenCalledWith(1, null, null)
  })

  test('taxonomy manager submits style name and prompt', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    render(
      <TaxonomyManager
        kind="style"
        items={[]}
        isAdmin
        createOpen
        onCreateOpenChange={vi.fn()}
        onChanged={onChanged}
      />,
    )

    expect(screen.getByRole('dialog', { name: '新增图片风格' })).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('输入图片风格名称'), '电影感')
    const promptEditor = screen.getByPlaceholderText('输入提示词')
    expect(promptEditor.tagName.toLowerCase()).toBe('textarea')
    await user.type(promptEditor, 'cinematic light')
    await user.click(screen.getByRole('button', { name: '新增' }))

    await waitFor(() => {
      expect(createTaxonomyMock).toHaveBeenCalledWith('style', '电影感', 'cinematic light')
      expect(onChanged).toHaveBeenCalled()
    })
  })

  test('image labels omit empty style and classification', () => {
    expect(imageLabels(referenceImageWithoutOptionalLabels)).toEqual(['衬衫'])
  })

  test('taxonomy manager localizes edit save button', async () => {
    const user = userEvent.setup()
    render(
      <TaxonomyManager
        kind="category"
        items={[category]}
        isAdmin
        onChanged={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: '编辑' }))
    expect(screen.getByRole('dialog', { name: '编辑类目' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    expect(screen.queryByText('common.save')).not.toBeInTheDocument()
  })
})

export const referenceImageWithoutOptionalLabels: ReferenceImageRead = {
  id: 1,
  url: '/image.png',
  name: 'image.png',
  category_id: 1,
  category_name: '衬衫',
  style_id: null,
  style_name: null,
  style_prompt: null,
  classification_id: null,
  classification_name: null,
  classification_prompt: null,
  created_at: '2026-06-21T00:00:00',
  updated_at: '2026-06-21T00:00:00',
}
