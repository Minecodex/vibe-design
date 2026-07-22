import { forwardRef, useEffect, useImperativeHandle } from 'react'
import { beforeEach, vi } from 'vitest'
import { Workbook } from 'exceljs'

import { __homeModelCatalogLoaderTestUtils } from './components/homeModelCatalogLoader'
import type { HomeChatOfficeSheetSnapshot } from './components/homeChatOfficeSnapshots'
import { __homeHarnessMetadataLoaderTestUtils } from './homeHarnessMetadataLoader'

export const storeState = {
  conversationId: 42,
  projectId: 1,
  messages: [],
  isStreaming: false,
  runStatus: 'idle' as const,
  streamingBlocks: [],
  mode: 'fast' as const,
  artifactMode: 'web' as const,
  setMode: vi.fn(),
  setArtifactMode: vi.fn(),
  webSearchEnabled: false,
  setWebSearchEnabled: vi.fn(),
  activeSkillId: null,
  skillSelectionMode: 'auto' as const,
  selectedDesignSystemId: null,
  skillDecisionReason: null,
  activateSkill: vi.fn(),
  selectDesignSystem: vi.fn(),
  conversations: [],
  conversationsHasMore: false,
  workspaceFiles: [],
  engineVersion: 'harness' as const,
  userInteraction: null,
  sendMessage: vi.fn(),
  stopStreaming: vi.fn(),
  newChat: vi.fn(),
  loadConversations: vi.fn(),
  loadConversation: vi.fn(),
  loadMoreConversations: vi.fn(),
  loadOlderMessages: vi.fn(),
  olderMessagesHasMore: false,
  olderMessagesLoading: false,
  createHarnessConversation: vi.fn(),
  loadUiConfig: vi.fn(),
  respondToAgent: vi.fn(),
  startExecution: vi.fn(),
  revisePlan: vi.fn(),
  patchCurrentOutline: vi.fn(),
  upsertWorkspaceFile: vi.fn(),
  modelPreferences: {},
  setModelPreferences: vi.fn(),
  uiConfig: {
    hiddenToolCalls: [],
  },
}

export const providersListMock = vi.fn()
export const providersRegistryMock = vi.fn()
export const providersModelsMock = vi.fn()
export const assetsProjectSummariesMock = vi.fn()
export const assetsListMock = vi.fn()
export const uploadAttachmentMock = vi.fn()
export const listHarnessSkillsMock = vi.fn()
export const getHarnessSkillExampleHtmlMock = vi.fn()
export const listHarnessDesignSystemsMock = vi.fn()
export const getHarnessDesignSystemMock = vi.fn()
export const getHarnessDesignSystemPreviewHtmlUrlMock = vi.fn()
export const getWorkspaceFileUrlMock = vi.fn()
export const fetchWorkspaceFileBlobMock = vi.fn()
export const fetchWorkspaceFileVersionBlobMock = vi.fn()
export const getWorkspaceHtmlBundleUrlMock = vi.fn()
export const fetchWorkspaceHtmlBundleBlobMock = vi.fn()
export const createWorkspacePreviewTokenMock = vi.fn()
export const getWorkspaceHtmlPreviewUrlMock = vi.fn()
export const getWorkspaceHtmlVersionPreviewUrlMock = vi.fn()
export const getWorkspacePreviewFileVersionUrlMock = vi.fn()
export const getWorkspacePreviewFileUrlMock = vi.fn()
export const openWorkspaceOfficeSessionMock = vi.fn()
export const saveWorkspaceOfficeSessionMock = vi.fn()
export const closeWorkspaceOfficeSessionMock = vi.fn()
export const toastErrorMock = vi.fn()
export const toastSuccessMock = vi.fn()
export const upsertWorkspaceFileMock = storeState.upsertWorkspaceFile
export const sharedStoreSetStateMock = vi.fn()
export const scrollToMock = vi.fn()
export const authStoreState = {
  user: {
    id: 1,
    email: 'tester@example.com',
    username: 'tester',
    role: 'user',
    is_active: true,
    balance_cents: 1000,
  },
}
export let latestSheetEditorSnapshot: HomeChatOfficeSheetSnapshot | null = null
let mockLanguage = 'en-US'

export async function createXlsxBase64Workbook(): Promise<string> {
  const workbook = new Workbook()
  const budgetSheet = workbook.addWorksheet('Budget')
  budgetSheet.getCell('A1').value = 'Item'
  budgetSheet.getCell('B1').value = 'Amount'
  budgetSheet.getCell('A2').value = 'Tea'
  budgetSheet.getCell('B2').value = 18
  budgetSheet.getColumn(2).width = 16
  budgetSheet.views = [{ state: 'frozen', ySplit: 1 }]
  workbook.views = [{
    x: 0,
    y: 0,
    width: 16000,
    height: 9000,
    firstSheet: 0,
    activeTab: 0,
    visibility: 'visible',
  }]

  const buffer = await workbook.xlsx.writeBuffer()
  return Buffer.from(buffer).toString('base64')
}

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: vi.fn(),
  },
  useTranslation: () => ({
    i18n: {
      language: mockLanguage,
    },
    t: (
      key: string,
      fallback?: string | { defaultValue?: string; count?: number; page?: number },
    ) => {
      const map: Record<string, string> = {
        'canvas.chat.history.web_search': 'Web Search',
        'canvas.chat.history.web_search_hint': 'Search for real-time information',
        'canvas.chat.modes.thinking': 'Thinking Mode',
        'canvas.chat.modes.thinking_desc': 'Use deeper reasoning before answering',
        'canvas.chat.modes.quick': 'Quick Mode',
        'canvas.chat.modes.quick_desc': 'Respond faster with lighter reasoning',
        'providers.multimodal': 'Multimodal',
        'home.chat.model_settings': 'Model Settings',
        'home.chat.current_image_model': 'Current image model',
        'home.chat.current_video_model': 'Current video model',
        'home.chat.current_multimodal_model': 'Current multimodal model',
        'home.chat.local_upload': 'Local Upload',
        'home.chat.asset_library': 'Asset Library',
        'home.ppt.regenerate_prompt': 'Help me regenerate slide {{page}} in the PPT',
        'common.download': 'Localized Download',
      }

      const localizedMap: Record<string, { zh: string; en: string }> = {
        'home.modes.web': { zh: '网页模式', en: 'Web Mode' },
        'home.modes.document': { zh: '文档模式', en: 'Document Mode' },
        'home.modes.spreadsheet': { zh: '表格模式', en: 'Spreadsheet Mode' },
        'home.modes.slides': { zh: '幻灯片', en: 'Slides' },
        'home.modes.image': { zh: '图片模式', en: 'Image Mode' },
        'home.modes.video': { zh: '视频模式', en: 'Video Mode' },
        'home.runtime.phaseValue.planning': { zh: '规划中', en: 'Planning' },
        'home.runtime.phaseValue.planning_ready': { zh: '待执行', en: 'Ready' },
        'home.runtime.phaseValue.revising_plan': { zh: '调整大纲中', en: 'Revising' },
        'home.runtime.phaseValue.execution_prepare': { zh: '准备执行', en: 'Preparing' },
        'home.runtime.phaseValue.executing': { zh: '执行中', en: 'Executing' },
        'home.runtime.phaseValue.completed': { zh: '已完成', en: 'Completed' },
        'home.runtime.phaseValue.failed': { zh: '失败', en: 'Failed' },
        'home.runtime.status.idle': { zh: '未开始', en: 'Idle' },
        'home.runtime.status.running': { zh: '进行中', en: 'Running' },
        'home.runtime.status.waiting_input': { zh: '等待输入', en: 'Waiting for input' },
        'home.runtime.status.completed': { zh: '已完成', en: 'Completed' },
        'home.runtime.status.failed': { zh: '失败', en: 'Failed' },
        'home.runtime.status.blocked': { zh: '已阻塞', en: 'Blocked' },
        'home.runtime.status.cancelled': { zh: '已取消', en: 'Cancelled' },
        'home.chat.upload_unsupported_format': { zh: '仅支持上传文本文件和 Office 文件。', en: 'Only supported text and Office files can be uploaded.' },
      }

      if (map[key]) {
        return map[key].replace('{{page}}', String(fallback && typeof fallback !== 'string' ? fallback.page ?? '' : ''))
      }

      if (localizedMap[key]) {
        return mockLanguage === 'zh-CN' ? localizedMap[key].zh : localizedMap[key].en
      }

      if (typeof fallback === 'string') {
        return fallback
      }

      if (fallback?.defaultValue) {
        return Object.entries(fallback).reduce((text, [placeholder, value]) => (
          placeholder === 'defaultValue'
            ? text
            : text.split(`{{${placeholder}}}`).join(String(value ?? ''))
        ), fallback.defaultValue)
      }

      return key
    },
  }),
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/store/appConfigStore', () => ({
  useAppConfigStore: (selector: (state: { appName: string; appNameEn: string }) => unknown) =>
    selector({
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
    }),
}))

vi.mock('@/store/homeHarnessStore', () => {
  const useChatStore = () => storeState
  ;(useChatStore as typeof useChatStore & { getState: () => typeof storeState }).getState = () => storeState
  ;(useChatStore as typeof useChatStore & { setState: (partial: Partial<typeof storeState>) => void }).setState = (partial) => {
    sharedStoreSetStateMock(partial)
    Object.assign(storeState, partial)
  }
  return { useChatStore }
})

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authStoreState) => unknown) => (
    typeof selector === 'function' ? selector(authStoreState) : authStoreState
  ),
}))

vi.mock('@/api/endpoints/providers', () => ({
  providersApi: {
    list: (...args: unknown[]) => providersListMock(...args),
    getRegistry: (...args: unknown[]) => providersRegistryMock(...args),
    listModels: (...args: unknown[]) => providersModelsMock(...args),
  },
}))

vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    listProjectSummaries: (...args: unknown[]) => assetsProjectSummariesMock(...args),
    list: (...args: unknown[]) => assetsListMock(...args),
  },
  getAssetListMediaUrl: (asset: { asset_type?: string, list_preview_url?: string | null, url: string }) =>
    asset.asset_type === 'image' ? (asset.list_preview_url ?? asset.url) : asset.url,
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getWorkspaceFileUrl: (...args: unknown[]) => getWorkspaceFileUrlMock(...args),
    fetchWorkspaceFileBlob: (...args: unknown[]) => fetchWorkspaceFileBlobMock(...args),
    fetchWorkspaceFileVersionBlob: (...args: unknown[]) => fetchWorkspaceFileVersionBlobMock(...args),
    getWorkspaceHtmlBundleUrl: (...args: unknown[]) => getWorkspaceHtmlBundleUrlMock(...args),
    fetchWorkspaceHtmlBundleBlob: (...args: unknown[]) => fetchWorkspaceHtmlBundleBlobMock(...args),
    createWorkspacePreviewToken: (...args: unknown[]) => createWorkspacePreviewTokenMock(...args),
    getWorkspaceHtmlPreviewUrl: (...args: unknown[]) => getWorkspaceHtmlPreviewUrlMock(...args),
    getWorkspaceHtmlVersionPreviewUrl: (...args: unknown[]) => getWorkspaceHtmlVersionPreviewUrlMock(...args),
    getWorkspacePreviewFileUrl: (...args: unknown[]) => getWorkspacePreviewFileUrlMock(...args),
    getWorkspacePreviewFileVersionUrl: (...args: unknown[]) => getWorkspacePreviewFileVersionUrlMock(...args),
    openWorkspaceOfficeSession: (...args: unknown[]) => openWorkspaceOfficeSessionMock(...args),
    saveWorkspaceOfficeSession: (...args: unknown[]) => saveWorkspaceOfficeSessionMock(...args),
    closeWorkspaceOfficeSession: (...args: unknown[]) => closeWorkspaceOfficeSessionMock(...args),
    uploadAttachment: (...args: unknown[]) => uploadAttachmentMock(...args),
    uploadHarnessAttachment: (...args: unknown[]) => uploadAttachmentMock(...args),
    listHarnessSkills: (...args: unknown[]) => listHarnessSkillsMock(...args),
    getHarnessSkillExampleHtml: (...args: unknown[]) => getHarnessSkillExampleHtmlMock(...args),
    listHarnessDesignSystems: (...args: unknown[]) => listHarnessDesignSystemsMock(...args),
    getHarnessDesignSystem: (...args: unknown[]) => getHarnessDesignSystemMock(...args),
    getHarnessDesignSystemPreviewHtmlUrl: (...args: unknown[]) => getHarnessDesignSystemPreviewHtmlUrlMock(...args),
  },
  isHarnessWorkspaceRelativePath: (filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    return !!raw && !raw.startsWith('http://') && !raw.startsWith('https://') && !raw.startsWith('data:')
      && !raw.startsWith('blob:') && !raw.startsWith('/')
  },
  normalizeHarnessWorkspacePath: (filePath: string) =>
    String(filePath || '').trim().replace(/\\/g, '/').replace(/^\/+/, ''),
  isHtmlWorkspaceFilePath: (filePath: string | null | undefined) => {
    const normalized = String(filePath || '').trim().replace(/\\/g, '/').replace(/^\/+/, '')
    return normalized.endsWith('.html') || normalized.endsWith('.htm')
  },
  resolveHarnessWorkspaceUrl: (
    conversationId: string | number | null | undefined,
    filePath: string | null | undefined,
  ) => {
    const normalized = String(filePath || '').trim().replace(/\\/g, '/').replace(/^\/+/, '')
    if (!normalized || normalized.startsWith('http://') || normalized.startsWith('https://') || normalized.startsWith('/')) {
      return normalized || undefined
    }
    if (conversationId == null || conversationId === '') {
      return normalized
    }
    return getWorkspaceFileUrlMock(String(conversationId), normalized)
  },
}))

vi.mock('sonner', () => ({
  Toaster: () => null,
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}))

vi.mock('./components/HomeChatDocHtmlPreview', () => ({
  HomeChatDocHtmlPreview: ({
    previewFilePath,
    onPresentationRegenerateSlide,
    isPresentationRegenerateDisabled,
  }: {
    previewFilePath: string
    onPresentationRegenerateSlide?: ((slideIndex: number) => void) | undefined
    isPresentationRegenerateDisabled?: boolean | undefined
  }) => (
    <div data-testid="home-chat-doc-html-preview">
      <div>{previewFilePath}</div>
      <button
        type="button"
        data-testid="home-chat-doc-html-preview-regenerate-slide-2"
        disabled={isPresentationRegenerateDisabled}
        onClick={() => onPresentationRegenerateSlide?.(2)}
      >
        Regenerate slide 2
      </button>
    </div>
  ),
}))

vi.mock('./components/HomeChatUniverSheetEditor', () => ({
  HomeChatUniverSheetEditor: forwardRef(({
    onDirtyChange,
    snapshot,
  }: {
    onDirtyChange?: (dirty: boolean) => void
    snapshot: HomeChatOfficeSheetSnapshot
  }, ref) => {
    latestSheetEditorSnapshot = snapshot

    useEffect(() => {
      onDirtyChange?.(true)
    }, [onDirtyChange])

    useImperativeHandle(ref, () => ({
      getSavePayload: () => ({
        kind: 'sheet',
        sheetOrder: ['sheet-1'],
        activeSheetId: 'sheet-1',
        sheets: {
          'sheet-1': {
            id: 'sheet-1',
            name: 'Budget',
            rows: {
              '0': { h: 24 },
            },
            cols: {
              '1': { w: 16 },
            },
            cells: {
              '0:0': { v: 'Item', t: 's' },
              '0:1': { v: 'Amount', t: 's' },
              '1:0': { v: 'Tea', t: 's' },
              '1:1': { v: 18, t: 'n' },
            },
            merges: [],
            freeze: {
              rowSplit: 1,
              colSplit: 0,
            },
          },
        },
        styles: {
          'style-1': {
            font: {
              bold: true,
            },
          },
        },
      }),
      resetDirtyState: () => {
        onDirtyChange?.(false)
      },
    }))

    return <div data-testid="home-chat-univer-sheet-editor" />
  }),
}))

vi.mock('./components/HomeChatPptPreview', () => ({
  HomeChatPptPreview: () => <div data-testid="home-chat-office-presentation-preview" />,
}))

export function setMockLanguage(language: string) {
  mockLanguage = language
}

  beforeEach(() => {
    mockLanguage = 'en-US'
    __homeModelCatalogLoaderTestUtils.reset()
    __homeHarnessMetadataLoaderTestUtils.reset()
    vi.unstubAllGlobals()
    localStorage.clear()
    window.history.replaceState({}, '', '/dashboard/home')
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:workspace-media'),
      revokeObjectURL: vi.fn(),
    })
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    Object.defineProperty(window.HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      value: scrollToMock,
    })
    window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined)
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

    Object.assign(storeState, {
      conversationId: 42,
      projectId: 1,
      messages: [],
      isStreaming: false,
      runStatus: 'idle',
      streamingBlocks: [],
      activeUserPlan: null,
      outlineRuntime: null,
      mode: 'fast',
      artifactMode: 'web',
      webSearchEnabled: false,
      activeSkillId: null,
      selectedDesignSystemId: null,
      conversations: [],
      conversationsHasMore: false,
      olderMessagesHasMore: false,
      olderMessagesLoading: false,
      workspaceFiles: [],
      runtimeState: null,
      engineVersion: 'harness',
  userInteraction: null,
      modelPreferences: {},
      uiConfig: {
        hiddenToolCalls: [],
      },
    })
    authStoreState.user = {
      id: 1,
      email: 'tester@example.com',
      username: 'tester',
      role: 'user',
      is_active: true,
      balance_cents: 1000,
    }

    storeState.setMode.mockReset()
    storeState.setArtifactMode.mockReset()
    storeState.setWebSearchEnabled.mockReset()
    storeState.activateSkill.mockReset()
    storeState.selectDesignSystem.mockReset()
    storeState.sendMessage.mockReset()
    storeState.stopStreaming.mockReset()
    storeState.newChat.mockReset()
    storeState.loadConversations.mockReset()
    storeState.loadConversation.mockReset()
    storeState.loadMoreConversations.mockReset()
    storeState.loadOlderMessages.mockReset()
    storeState.createHarnessConversation.mockReset()
    storeState.loadUiConfig.mockReset()
    storeState.respondToAgent.mockReset()
    storeState.startExecution.mockReset()
    storeState.revisePlan.mockReset()
    storeState.patchCurrentOutline.mockReset()
    storeState.upsertWorkspaceFile.mockReset()
    storeState.setModelPreferences.mockReset()
    sharedStoreSetStateMock.mockReset()
    scrollToMock.mockReset()

    providersListMock.mockReset()
    providersRegistryMock.mockReset()
    providersModelsMock.mockReset()
    assetsProjectSummariesMock.mockReset()
    assetsListMock.mockReset()
    uploadAttachmentMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    listHarnessSkillsMock.mockReset()
    getHarnessSkillExampleHtmlMock.mockReset()
    listHarnessDesignSystemsMock.mockReset()
    getHarnessDesignSystemMock.mockReset()
    getHarnessDesignSystemPreviewHtmlUrlMock.mockReset()
    getWorkspaceFileUrlMock.mockReset()
    fetchWorkspaceFileBlobMock.mockReset()
    fetchWorkspaceFileVersionBlobMock.mockReset()
    getWorkspaceHtmlBundleUrlMock.mockReset()
    fetchWorkspaceHtmlBundleBlobMock.mockReset()
    createWorkspacePreviewTokenMock.mockReset()
    getWorkspaceHtmlPreviewUrlMock.mockReset()
    getWorkspaceHtmlVersionPreviewUrlMock.mockReset()
    getWorkspacePreviewFileUrlMock.mockReset()
    getWorkspacePreviewFileVersionUrlMock.mockReset()
    openWorkspaceOfficeSessionMock.mockReset()
    saveWorkspaceOfficeSessionMock.mockReset()
    closeWorkspaceOfficeSessionMock.mockReset()
    latestSheetEditorSnapshot = null

    listHarnessSkillsMock.mockResolvedValue({ data: [] })
    getHarnessSkillExampleHtmlMock.mockResolvedValue({ data: '<!doctype html><html><body>preview</body></html>' })
    listHarnessDesignSystemsMock.mockResolvedValue({ data: [] })
    getHarnessDesignSystemPreviewHtmlUrlMock.mockImplementation(
      (designSystemId: string) => `http://localhost:8000/api/v1/agent/harness/design-systems/${encodeURIComponent(designSystemId)}/preview-html`,
    )
    storeState.setArtifactMode.mockImplementation((mode) => {
      storeState.artifactMode = mode
    })
    storeState.activateSkill.mockImplementation((skillId) => {
      storeState.activeSkillId = skillId as any
    })
    storeState.selectDesignSystem.mockImplementation((designSystemId) => {
      storeState.selectedDesignSystemId = designSystemId as any
    })
    storeState.upsertWorkspaceFile.mockImplementation((conversationId, file) => {
      const nextWorkspaceFiles = [...(storeState.workspaceFiles as any[]), file]
      sharedStoreSetStateMock({
        conversationId: String(conversationId),
        workspaceFiles: nextWorkspaceFiles,
      })
      storeState.workspaceFiles = nextWorkspaceFiles as never
    })
    providersListMock.mockResolvedValue({
      data: [
        {
          code: 'builtin',
          name: 'Builtin',
          status: 'authorized',
          is_builtin: true,
        },
      ],
    })
    providersRegistryMock.mockResolvedValue({
      data: {
        builtin: {
          models: {
            text2image: [
              { model_name: 'img-fast', label: 'Image Fast', description: 'Image default' },
            ],
            text2video: [
              { model_name: 'vid-fast', label: 'Video Fast', description: 'Video default' },
            ],
            multimodal: [
              {
                model_name: 'mm-fast',
                label: 'Fast Vision',
                description: 'Fast only',
                config: { supports_fast_mode: true, supports_thinking_mode: false },
              },
              {
                model_name: 'mm-think',
                label: 'Think Vision',
                description: 'Thinking only',
                config: { supports_fast_mode: false, supports_thinking_mode: true, thinking_variant_of: 'mm-fast' },
              },
            ],
          },
        },
      },
    })
    providersModelsMock.mockResolvedValue({
      data: [
        { model_name: 'img-fast', model_type: 'text2image', is_enabled: true },
        { model_name: 'vid-fast', model_type: 'text2video', is_enabled: true },
        { model_name: 'mm-fast', model_type: 'multimodal', is_enabled: true },
        { model_name: 'mm-think', model_type: 'multimodal', is_enabled: true },
      ],
    })
    assetsProjectSummariesMock.mockResolvedValue({
      data: [
        {
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 1,
          image_count: 1,
          video_count: 0,
          latest_asset_updated_at: '2026-04-01T12:00:00',
        },
      ],
    })
    assetsListMock.mockResolvedValue({
      data: [
        {
          id: 1,
          project_id: 7,
          user_id: 1,
          url: 'https://example.com/library-asset.png',
          asset_type: 'image',
          origin_kind: 'local_upload',
          source_asset_id: null,
          created_at: '2026-04-01T11:00:00',
          updated_at: '2026-04-01T12:00:00',
          is_favorite: false,
          project_name: 'Brand Refresh',
          canvas_item_id: null,
        },
      ],
    })
    uploadAttachmentMock.mockResolvedValue({
      data: {
        url: 'references/inputs/upload_abc123/source.png',
        filename: 'demo.png',
        type: 'image',
        size: 123,
      },
    })
    openWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-session-default',
        file_path: 'default.docx',
        file_kind: 'doc',
        engine: 'univer',
        unit_id: 'unit-default',
        readonly: false,
      },
    })
    saveWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-session-default',
        file_path: 'default.docx',
        saved_at: '2026-04-25T02:00:00.000Z',
      },
    })
    closeWorkspaceOfficeSessionMock.mockResolvedValue({
      data: {
        session_id: 'office-session-default',
        closed: true,
      },
    })
    getWorkspaceFileUrlMock.mockImplementation((conversationId: string | number, filePath: string) =>
      `/api/v1/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(filePath)}`,
    )
    createWorkspacePreviewTokenMock.mockResolvedValue({
      preview_token: 'preview-token',
      expires_in_seconds: 300,
    })
    getWorkspacePreviewFileUrlMock.mockImplementation((
      conversationId: string | number,
      filePath: string,
      previewToken: string,
      options?: { width?: number },
    ) => {
      const widthParam = options?.width ? `&w=${options.width}` : ''
      return `/api/v1/agent/harness/conversations/${conversationId}/preview-files/${encodeURIComponent(filePath)}?preview_token=${previewToken}${widthParam}`
    })
  })



