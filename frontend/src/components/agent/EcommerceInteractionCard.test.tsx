import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PendingInteraction } from '@/api/endpoints/agent'

import { EcommerceInteractionCard, isEcommerceInteractionKind } from './EcommerceInteractionCard'

const createWorkspacePreviewTokenMock = vi.fn()
const getHarnessGenerationArtifactTaskMock = vi.fn()
const listCategoriesMock = vi.fn()
const listStylesMock = vi.fn()

vi.mock('@/config/runtimeConfig', () => ({
  getApiOrigin: () => 'http://localhost:8000',
  getApiBaseUrl: () => 'http://localhost:8000/api/v1',
}))

vi.mock('@/api/endpoints/referenceGallery', () => ({
  referenceGalleryApi: {
    listCategories: (...args: unknown[]) => listCategoriesMock(...args),
    listStyles: (...args: unknown[]) => listStylesMock(...args),
  },
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    createWorkspacePreviewToken: (...args: unknown[]) => createWorkspacePreviewTokenMock(...args),
    getHarnessGenerationArtifactTask: (...args: unknown[]) => getHarnessGenerationArtifactTaskMock(...args),
    getWorkspacePreviewFileUrl: (conversationId: string, filePath: string, previewToken: string, options?: { width?: number }) => {
      const width = Number(options?.width || 0)
      const widthParam = width > 0 ? `&w=${Math.round(width)}` : ''
      return `http://localhost:8000/api/v1/agent/harness/conversations/${conversationId}/preview-files/${encodeURIComponent(filePath)}?preview_token=${previewToken}${widthParam}`
    },
  },
  isHarnessWorkspaceRelativePath: (filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    return raw.startsWith('references/') || raw.startsWith('generated/') || raw.startsWith('file_versions/')
  },
  normalizeHarnessWorkspacePath: (filePath: string) => String(filePath || '').trim().replace(/\\/g, '/').replace(/^\/+/, ''),
  resolveHarnessWorkspaceUrl: (conversationId: string | number | null | undefined, filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    if (!raw) {
      return undefined
    }
    if (/^(?:https?:|data:|blob:|\/)/.test(raw)) {
      return raw
    }
    if (!conversationId) {
      return raw
    }
    return `http://localhost:8000/api/v1/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(raw)}`
  },
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  const translations: Record<string, string> = {
    'agent.ecommerceInteraction.options.title': '商品图生成配置',
    'agent.ecommerceInteraction.options.subtitle': '选择分类、风格、参考图和生成数量',
    'agent.ecommerceInteraction.options.category': '参考图库图片分类',
    'agent.ecommerceInteraction.options.categoryPlaceholder': '选择图片分类',
    'agent.ecommerceInteraction.options.style': '图片风格',
    'agent.ecommerceInteraction.options.stylePlaceholder': '选择图片风格',
    'agent.ecommerceInteraction.options.enableBackground': '开启背景图',
    'agent.ecommerceInteraction.options.enableModel': '开启人物参考图',
    'agent.ecommerceInteraction.options.enableOtherMain': '开启其他商品主图参考图',
    'agent.ecommerceInteraction.options.generationCount': '生成商品图数量',
    'agent.ecommerceInteraction.actions.submit': '提交',
    'agent.ecommerceInteraction.actions.cancel': '取消',
    'agent.ecommerceInteraction.actions.addReference': '添加参考图',
    'agent.ecommerceInteraction.actions.removeReference': '移除参考图',
    'agent.ecommerceInteraction.actions.pickFromAssetLibrary': '选择资产库',
    'agent.ecommerceInteraction.actions.pickFromReferenceGallery': '选择参考图库',
    'agent.ecommerceInteraction.references.addCard': '添加参考图',
    'agent.ecommerceInteraction.references.localUpload': '本地上传',
    'agent.ecommerceInteraction.references.uploading': '上传中',
    'agent.ecommerceInteraction.references.uploadFailed': '参考图上传失败',
    'agent.ecommerceInteraction.references.limitHint': '{{current}} / {{count}} 张参考图',
    'agent.ecommerceInteraction.references.limitReached': '最多可添加 {{count}} 张参考图',
    'agent.ecommerceInteraction.references.background': '背景图',
    'agent.ecommerceInteraction.references.model': '人物参考图',
    'agent.ecommerceInteraction.references.otherMain': '其他商品主图参考图',
    'agent.ecommerceInteraction.submitted': '已提交',
    'agent.ecommerceInteraction.imageAlt': '参考图 {{index}}',
    'agent.ecommerceInteraction.taxonomy.loadFailed': '参考图库分类加载失败',
  }
  const t = (key: string, values?: Record<string, unknown>) => {
        const template = translations[key] ?? key
        return Object.entries(values || {}).reduce(
          (text, [name, value]) => text.split(`{{${name}}}`).join(String(value)),
          template,
        )
      }
  return {
    ...actual,
    useTranslation: () => ({
      t,
    }),
  }
})

const categories = [
  {
    id: 1,
    kind: 'category',
    name: '夹克',
    prompt: '夹克分类提示词',
    image_count: 2,
    created_at: '',
    updated_at: '',
  },
]

const styles = [
  {
    id: 2,
    kind: 'style',
    name: '都市通勤',
    prompt: '都市通勤风格提示词',
    image_count: 3,
    created_at: '',
    updated_at: '',
  },
]

function interaction(overrides: Record<string, any> = {}): PendingInteraction {
  return {
    request_id: 'req-options',
    kind: 'ecommerce_generation_options',
    status: 'pending',
    defaults: {
      generation_count: 4,
      generation_count_min: 1,
      generation_count_max: 6,
    },
    ...overrides,
  }
}

async function chooseSelect(label: string, option: string) {
  const trigger = await screen.findByLabelText(label)
  await waitFor(() => expect(trigger).not.toBeDisabled())
  trigger.focus()
  fireEvent.keyDown(trigger, { key: 'ArrowDown' })
  await userEvent.click(await screen.findByRole('option', { name: option }))
}

describe('EcommerceInteractionCard', () => {
  beforeEach(() => {
    Object.defineProperty(window.HTMLElement.prototype, 'hasPointerCapture', {
      configurable: true,
      value: vi.fn(() => false),
    })
    Object.defineProperty(window.HTMLElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: vi.fn(),
    })
    Object.defineProperty(window.HTMLElement.prototype, 'releasePointerCapture', {
      configurable: true,
      value: vi.fn(),
    })
    Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    })
    createWorkspacePreviewTokenMock.mockReset()
    createWorkspacePreviewTokenMock.mockResolvedValue({
      preview_token: 'preview-token',
      expires_in_seconds: 300,
    })
    getHarnessGenerationArtifactTaskMock.mockReset()
    getHarnessGenerationArtifactTaskMock.mockResolvedValue({
      data: {
        status: 'completed',
        result_url: '/api/v1/uploads/generated/artifact.png',
      },
    })
    listCategoriesMock.mockReset()
    listCategoriesMock.mockResolvedValue({ data: categories })
    listStylesMock.mockReset()
    listStylesMock.mockResolvedValue({ data: styles })
  })

  it('recognizes only the new ecommerce generation options kind', () => {
    expect(isEcommerceInteractionKind('ecommerce_generation_options')).toBe(true)
    expect(isEcommerceInteractionKind(['ecommerce', 'analysis', 'review'].join('_'))).toBe(false)
    expect(isEcommerceInteractionKind(['ecommerce', 'generation', 'review'].join('_'))).toBe(false)
  })

  it('renders category, style, switches, count, submit, and cancel', async () => {
    render(<EcommerceInteractionCard interaction={interaction()} onRespond={vi.fn()} />)

    expect(await screen.findByText('商品图生成配置')).toBeInTheDocument()
    expect(screen.getByLabelText('参考图库图片分类')).toBeInTheDocument()
    expect(screen.getByLabelText('图片风格')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: '开启背景图' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: '开启人物参考图' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: '开启其他商品主图参考图' })).toBeInTheDocument()
    expect(screen.getByLabelText('生成商品图数量')).toHaveValue(4)
    expect(screen.getByRole('button', { name: '提交' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '取消' })).toBeEnabled()
  })

  it('loads taxonomy choices and sends selected prompts in submit payload', async () => {
    const onRespond = vi.fn()
    render(<EcommerceInteractionCard interaction={interaction()} onRespond={onRespond} />)

    await chooseSelect('参考图库图片分类', '夹克')
    await chooseSelect('图片风格', '都市通勤')
    fireEvent.change(screen.getByLabelText('生成商品图数量'), { target: { value: '6' } })
    await userEvent.click(screen.getByRole('button', { name: '提交' }))

    expect(onRespond).toHaveBeenCalledWith(
      'req-options',
      'confirm',
      '提交',
      expect.objectContaining({
        action: 'confirm',
        category_id: 1,
        category_name: '夹克',
        category_prompt: '夹克分类提示词',
        style_id: 2,
        style_name: '都市通勤',
        style_prompt: '都市通勤风格提示词',
        generation_count: 6,
      }),
    )
  })

  it('shows reference upload UI when switches are enabled', async () => {
    render(<EcommerceInteractionCard interaction={interaction()} onRespond={vi.fn()} />)

    await userEvent.click(screen.getByRole('switch', { name: '开启背景图' }))
    await userEvent.click(screen.getByRole('switch', { name: '开启人物参考图' }))
    await userEvent.click(screen.getByRole('switch', { name: '开启其他商品主图参考图' }))

    expect(screen.getByText('背景图')).toBeInTheDocument()
    expect(screen.getByText('人物参考图')).toBeInTheDocument()
    expect(screen.getByText('其他商品主图参考图')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '添加参考图' })).toHaveLength(3)
  })

  it('shares the max reference image limit across all reference sections', async () => {
    const onRequestReferenceImages = vi.fn((_source, onSelect, _options) => {
      onSelect(['/api/v1/uploads/first.png', '/api/v1/uploads/second.png'])
    })
    render(
      <EcommerceInteractionCard
        interaction={interaction()}
        onRespond={vi.fn()}
        onRequestReferenceImages={onRequestReferenceImages}
        maxReferenceImages={2}
      />,
    )

    await userEvent.click(screen.getByRole('switch', { name: '开启背景图' }))
    await userEvent.click(screen.getByRole('switch', { name: '开启人物参考图' }))
    await userEvent.click(screen.getAllByRole('button', { name: '添加参考图' })[0])
    await userEvent.click(screen.getByText('选择参考图库'))

    await waitFor(() => expect(onRequestReferenceImages).toHaveBeenCalled())
    expect(onRequestReferenceImages.mock.calls[0][2]).toEqual({ maxSelection: 2 })
    expect(await screen.findAllByAltText(/参考图/)).toHaveLength(2)
    expect(screen.getAllByText('2 / 2 张参考图')).not.toHaveLength(0)

    const modelSection = screen.getByTestId('ecommerce-reference-section-人物参考图')
    const modelAddButton = within(modelSection).getByRole('button', { name: '添加参考图' })
    expect(modelAddButton).toBeDisabled()
  })

  it('sends only cancel action for cancel payload', async () => {
    const onRespond = vi.fn()
    render(<EcommerceInteractionCard interaction={interaction()} onRespond={onRespond} />)

    await userEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(onRespond).toHaveBeenCalledWith('req-options', 'cancel', '取消', { action: 'cancel' })
  })
})
