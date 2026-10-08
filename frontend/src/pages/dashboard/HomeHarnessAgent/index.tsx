import { DesignSystemSwatch } from './components/DesignSystemSwatch'
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Suspense, lazy } from 'react'
import { useIsDarkMode } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'
import {
  Globe,
  Send,
  Loader2,
  Eye,
  Check,
  ChevronDown,
  Plus,
  Maximize2,
  Minimize2,
  Folder,
  History,
  X,
} from 'lucide-react'
import { useChatStore, type ModelPreferences } from '@/store/homeHarnessStore'
import { useAuthStore } from '@/store/authStore'
import { useAppConfigStore } from '@/store/appConfigStore'
import {
  agentApi,
  isHarnessWorkspaceRelativePath,
  normalizeHarnessWorkspacePath,
  type AttachmentData,
  type HarnessDesignSystemRead,
  type HarnessSkillRead,
  type UserPlanRead,
  type WorkspaceFileRead,
} from '@/api/endpoints/agent'
import { toast } from 'sonner'
import { ensureBalanceOrNotify, isBalanceRequiredForMultimodalProvider } from '@/utils/balanceGuard'
import { validateUploadFileSize } from '@/utils/uploadLimits'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'

import { HomeChatMarkdown } from './components/HomeChatMarkdown'
import { HomeChatPlainTextPreview } from './components/HomeChatPlainTextPreview'
import { HomeChatModelPicker } from './components/HomeChatModelPicker'
import { HomeChatThinkingPicker } from './components/HomeChatThinkingPicker'
import {
  fillHomepageDefaultModelPreferences,
  getHomepageModeSwitchTargetMultimodalModel,
  isHomepageThinkingModeAvailableForModel,
  type HomeSelectableModel,
} from './components/homeChatModelPreferences'
import {
  HomeChatAssetLibraryModal,
  type HomeChatLibraryAsset,
} from './components/HomeChatAssetLibraryModal'
import { ReferenceGalleryPickerModal } from '../ReferenceGallery/ReferenceGalleryPickerModal'
import type { AssetLibrarySelectedAsset } from '../CanvasPage/AssetLibraryModal'
import type {
  EcommerceReferenceImageRequestOptions,
  EcommerceReferenceImageSource,
} from '@/components/agent/EcommerceInteractionCard'
import { HomeChatAttachmentPicker } from './components/HomeChatAttachmentPicker'
import { AttachmentCardStrip } from './components/AttachmentCardStrip'
import {
  filterSupportedHomeHarnessAttachmentFiles,
  inferHomeHarnessAttachmentKind,
} from './components/homeChatAttachmentKinds'
import { HomeHarnessMessageList } from './components/HomeHarnessMessageList'
import { HomeChatWorkspacePreviewRail } from './components/HomeChatWorkspacePreviewRail'
import { HomeChatFileVersionControl } from './components/HomeChatFileVersionControl'
import { HomeSessionFilesDialog } from './components/HomeSessionFilesDialog'
import {
  isSessionHtmlFile,
  isSessionMarkdownFile,
  isSessionOfficeDocFile,
  isSessionOfficeSheetFile,
  isSessionPresentationFile,
  isSessionTextLikeFile,
} from './components/homeChatWorkspaceFileKinds'
import { inferWorkspaceFileTypeFromPath } from './components/homeChatFinalAnswerFileReferences'
import {
  findUpdatedPreviewFile,
  findRuntimePreviewFile,
  shouldResetPreviewVersionSelection,
} from './components/homeChatPreviewVersionState'
import {
  buildSheetOfficeSessionSnapshot,
  collectSessionFiles,
  downloadWorkspaceBlob,
  getActivePreviewBaseFileVersion,
  getAttachmentNameFromUrl,
  getConversationModeLabel,
  getHomeSkillModePresentation,
  buildWorkspaceFileFromHarnessUpload,
  getLocalizedSkillDescription,
  getLocalizedSkillName,
  type HomeOpenWorkspaceOfficeSessionResponse,
  isHomeChatOfficeSheetSnapshot,
  isSessionImageFile,
  isSessionVideoFile,
  SKILL_MODES,
  summarizeConversationRuntime,
  type SessionFileItem,
} from './homeHarnessPageUtils'
import {
  buildExternalOpenTarget,
  getExternalOpenSuites,
  isExternalOpenSupported,
  openExternalTarget,
  type ExternalOpenSuite,
} from './components/homeChatExternalOpen'
import {
  filterFilesByTab,
  getFileTabCounts,
  type HomeChatFileTab,
} from './components/homeChatFileTabs'
import type {
  HomeChatOfficePresentationSnapshot,
} from './components/homeChatOfficeSnapshots'
import { HomeDesignSystemPreviewDialog } from './components/HomeDesignSystemPreviewDialog'
import { HomeSkillExamplePreviewDialog } from './components/HomeSkillExamplePreviewDialog'
import {
  getDesignSystemDisplayDescription,
  getDesignSystemDisplayTitle,
} from './components/homeDesignSystemPreviewUtils'
import { useHarnessMediaSource } from './components/useHarnessMediaSource'
import { loadHomepageModelCatalog } from './components/homeModelCatalogLoader'
import { deleteHomeForwardTransfer, loadHomeForwardTransfer } from './homeForwardTransfer'
import { loadHomeHarnessMetadata } from './homeHarnessMetadataLoader'
import {
  collectAttachmentBlobUrls,
  createPendingAttachmentId,
  enqueueLocalImageThumbnail,
  revokeAttachmentBlobUrls,
} from '../agentMedia/agentPendingAttachmentPreview'
import { useHomeChatMessageScroll } from './useHomeChatMessageScroll'
import {
  filterHomeVisibleSkills,
  getModeEntrySkillCandidates,
  type HomeArtifactMode,
  normalizeHomeArtifactMode,
  resolveConversationArtifactMode,
  supportsDesignSystem,
} from './homeArtifactModes'

export { HomeHarnessMessageList } from './components/HomeHarnessMessageList'

const HomeChatPptPreview = lazy(async () => ({
  default: (await import('./components/HomeChatPptPreview')).HomeChatPptPreview,
}))

const HomeChatDocHtmlPreview = lazy(async () => ({
  default: (await import('./components/HomeChatDocHtmlPreview')).HomeChatDocHtmlPreview,
}))

const HomeChatUniverSheetEditor = lazy(async () => ({
  default: (await import('./components/HomeChatUniverSheetEditor')).HomeChatUniverSheetEditor,
}))

const EMPTY_STATE_VISIBLE_MODES = SKILL_MODES.filter((mode) => mode.id !== 'image' && mode.id !== 'video')

function normalizePickerSearch(value: string): string {
  return value.trim().toLocaleLowerCase()
}

function resolveRuntimePreviewPath(
  artifactManifest: Record<string, any> | null | undefined,
  workspaceRuntimeSession: Record<string, any> | null | undefined,
  preparedWorkspace: Record<string, any> | null | undefined,
): string {
  return String(
    artifactManifest?.entry
    || workspaceRuntimeSession?.active_entry
    || preparedWorkspace?.entry_path
    || '',
  ).replace(/\\/g, '/').trim()
}

type TerminalFailureSource = {
  runtime_status?: string | null
  last_error_summary?: string | null
  runtime_state?: {
    failure?: { summary?: unknown, user_visible?: boolean } | null
  } | null
  failure?: { summary?: unknown, user_visible?: boolean } | null
}

function resolveVisibleTerminalFailureSummary(
  conversation: TerminalFailureSource | null | undefined,
  messages: { blocked: string, internal: string },
): string {
  const runtimeStatus = String(conversation?.runtime_status || '').toLowerCase()
  const isTerminalFailure = runtimeStatus === 'failed' || runtimeStatus === 'blocked' || runtimeStatus === 'cancelled'
  if (!isTerminalFailure) {
    return ''
  }

  const runtimeFailure = conversation?.runtime_state?.failure
  if (runtimeFailure?.user_visible === false) {
    return ''
  }

  const persistedFailure = conversation?.failure
  return String(
    runtimeFailure?.summary
    || (persistedFailure?.user_visible === false ? '' : persistedFailure?.summary)
    || conversation?.last_error_summary
    || (runtimeStatus === 'blocked'
      ? messages.blocked
      : runtimeStatus === 'failed'
        ? messages.internal
        : ''),
  ).trim()
}

async function resolveUploadedImageAttachmentPreviewUrl(
  conversationId: string | number,
  sourceUrl: string,
): Promise<string | undefined> {
  const workspacePath = isHarnessWorkspaceRelativePath(sourceUrl)
    ? normalizeHarnessWorkspacePath(sourceUrl)
    : ''
  if (!workspacePath) {
    return undefined
  }
  try {
    const { preview_token } = await agentApi.createWorkspacePreviewToken(String(conversationId))
    return agentApi.getWorkspacePreviewFileUrl(String(conversationId), workspacePath, preview_token, { width: 256 })
  } catch {
    return undefined
  }
}

// 鈹€鈹€ Helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

export function ChatHomePage() {
  const { t, i18n } = useTranslation()
  const appName = useAppConfigStore((state) => state.appName)
  const appNameEn = useAppConfigStore((state) => state.appNameEn)
  const isDark = useIsDarkMode()
  const { user } = useAuthStore()

  const {
    conversationId,
    messages,
    isStreaming,
    runStatus,
    streamingBlocks,
    setMode,
    activeSkillId,
    skillSelectionMode,
    selectedDesignSystemId,
    skillDecisionReason,
    activateSkill,
    selectDesignSystem,
    conversations,
    conversationsHasMore,
    workspaceFiles,
    runtimeState,
    outlineRuntime,
    userProgress,
    userInteraction,
    sendMessage,
    stopStreaming,
    newChat,
    loadConversations,
    loadConversation,
    loadMoreConversations,
    loadOlderMessages,
    createHarnessConversation,
    olderMessagesHasMore,
    olderMessagesLoading,
    respondToAgent,
    startExecution,
    revisePlan,
    patchCurrentOutline,
    upsertWorkspaceFile,
    modelPreferences,
    setModelPreferences,
    artifactMode,
    setArtifactMode,
    webSearchEnabled,
    setWebSearchEnabled,
    uiConfig,
    loadUiConfig,
  } = useChatStore()

  const [inputValue, setInputValue] = useState('')
  const [activeMode, setActiveMode] = useState<HomeArtifactMode>(artifactMode)
  const [availableSkills, setAvailableSkills] = useState<HarnessSkillRead[]>([])
  const [availableDesignSystems, setAvailableDesignSystems] = useState<HarnessDesignSystemRead[]>([])
  const [isFilesModalOpen, setIsFilesModalOpen] = useState(false)
  const [activeFileTab, setActiveFileTab] = useState<HomeChatFileTab>('all')
  const [previewingWorkspaceFile, setPreviewingWorkspaceFile] = useState<SessionFileItem | null>(null)
  const [previewingVersionId, setPreviewingVersionId] = useState<string | null>(null)
  const [previewingWorkspaceFileContent, setPreviewingWorkspaceFileContent] = useState('')
  const [previewingWorkspaceHtmlUrl, setPreviewingWorkspaceHtmlUrl] = useState<string | undefined>(undefined)
  const [previewingOfficeSession, setPreviewingOfficeSession] = useState<HomeOpenWorkspaceOfficeSessionResponse | null>(null)
  const [isOfficeSessionLoading, setIsOfficeSessionLoading] = useState(false)
  const [isOpeningExternalPreview, setIsOpeningExternalPreview] = useState(false)
  const [isWorkspaceFilePreviewLoading, setIsWorkspaceFilePreviewLoading] = useState(false)
  const [workspaceFilePreviewError, setWorkspaceFilePreviewError] = useState<string | null>(null)
  const [isDesignSystemPreviewOpen, setIsDesignSystemPreviewOpen] = useState(false)
  const [isSkillSelectOpen, setIsSkillSelectOpen] = useState(false)
  const [isDesignSystemSelectOpen, setIsDesignSystemSelectOpen] = useState(false)
  const [isSkillExamplePreviewOpen, setIsSkillExamplePreviewOpen] = useState(false)
  const [skillExamplePreviewSkill, setSkillExamplePreviewSkill] = useState<HarnessSkillRead | null>(null)
  const [skillSearchQuery, setSkillSearchQuery] = useState('')
  const [designSystemSearchQuery, setDesignSystemSearchQuery] = useState('')
  const [homeThinkingEnabled, setHomeThinkingEnabled] = useState(false)
  const [homeModelPreferences, setHomeModelPreferences] = useState(modelPreferences || {})
  const [homeAvailableImageModels, setHomeAvailableImageModels] = useState<HomeSelectableModel[]>([])
  const [homeAvailableMultimodalModels, setHomeAvailableMultimodalModels] = useState<HomeSelectableModel[]>([])
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentData[]>([])
  const trackedPendingAttachmentUrlsRef = useRef<string[]>([])
  useEffect(() => {
    const currentUrls = collectAttachmentBlobUrls(pendingAttachments)
    const currentSet = new Set(currentUrls)
    for (const url of trackedPendingAttachmentUrlsRef.current) {
      if (!currentSet.has(url)) {
        URL.revokeObjectURL(url)
      }
    }
    trackedPendingAttachmentUrlsRef.current = currentUrls
  }, [pendingAttachments])
  useEffect(() => () => {
    for (const url of trackedPendingAttachmentUrlsRef.current) {
      URL.revokeObjectURL(url)
    }
  }, [])
  const [submittingInteractionLabels, setSubmittingInteractionLabels] = useState<Record<string, string>>({})
  const [isAssetLibraryOpen, setIsAssetLibraryOpen] = useState(false)
  const [isReferenceGalleryPickerOpen, setIsReferenceGalleryPickerOpen] = useState(false)
  const [ecommerceReferenceImageSelect, setEcommerceReferenceImageSelect] = useState<{
    onSelect: (urls: string[]) => void
    maxSelection?: number
  } | null>(null)
  const [hoveredToolbarIcon, setHoveredToolbarIcon] = useState<string | null>(null)
  const [isDragActive, setIsDragActive] = useState(false)
  const [isComposerExpanded, setIsComposerExpanded] = useState(false)
  const activeConversation = conversations.find((conversation) => String(conversation.id) === String(conversationId ?? ''))
  const terminalFailureSummary = resolveVisibleTerminalFailureSummary(
    activeConversation as TerminalFailureSource | null | undefined,
    {
      blocked: t('home.chat.blocked_failure_message', 'Execution was blocked'),
      internal: t('home.chat.internal_failure_message', 'Internal error, execution stopped'),
    },
  )
  const displayedMode = conversationId
    ? resolveConversationArtifactMode(activeConversation)
    : activeMode

  useEffect(() => {
    setHomeModelPreferences((current) => {
      if (
        current.image_model === modelPreferences.image_model &&
        current.image_provider === modelPreferences.image_provider &&
        current.video_model === modelPreferences.video_model &&
        current.video_provider === modelPreferences.video_provider &&
        current.multimodal_model === modelPreferences.multimodal_model &&
        current.multimodal_provider === modelPreferences.multimodal_provider &&
        current.media_generation_settings === modelPreferences.media_generation_settings &&
        current.auto === modelPreferences.auto
      ) {
        return current
      }
      return modelPreferences || {}
    })
  }, [modelPreferences])
  const dragDepthRef = useRef(0)
  const forwardTransferHydratedRef = useRef(false)
  const currentLanguage = i18n.language || 'en-US'
  const {
    handleMessageScroll,
    loadOlderMessagesWithAnchor,
    scrollContainerRef,
  } = useHomeChatMessageScroll({
    conversationId,
    messageCount: messages.length,
    streamingBlockCount: streamingBlocks.length,
    olderMessagesHasMore,
    olderMessagesLoading,
    loadOlderMessages,
  })
  // Mirror the scroll container element into state so HomeHarnessMessageList can hand it to
  // react-virtuoso (customScrollParent). Stable callback ref → only runs on mount/unmount,
  // and still populates scrollContainerRef.current for useHomeChatMessageScroll.
  const [messageScrollEl, setMessageScrollEl] = useState<HTMLDivElement | null>(null)
  const setMessageScrollRef = useCallback((el: HTMLDivElement | null) => {
    const mutableScrollRef = scrollContainerRef as React.MutableRefObject<HTMLDivElement | null>
    mutableScrollRef.current = el
    setMessageScrollEl(el)
  }, [scrollContainerRef])
  const modeEntrySkillCandidates = useMemo(
    () => getModeEntrySkillCandidates(availableSkills, activeMode),
    [availableSkills, activeMode],
  )
  const filteredModeEntrySkillCandidates = useMemo(() => {
    const query = normalizePickerSearch(skillSearchQuery)
    if (!query) {
      return modeEntrySkillCandidates
    }
    return modeEntrySkillCandidates.filter((skill) => {
      const searchable = [
        skill.id,
        getLocalizedSkillName(skill, currentLanguage),
        getLocalizedSkillDescription(skill, currentLanguage),
      ].join(' ')
      return normalizePickerSearch(searchable).includes(query)
    })
  }, [currentLanguage, modeEntrySkillCandidates, skillSearchQuery])
  const filteredDesignSystems = useMemo(() => {
    const query = normalizePickerSearch(designSystemSearchQuery)
    if (!query) {
      return availableDesignSystems
    }
    return availableDesignSystems.filter((designSystem) => {
      const searchable = [
        designSystem.id,
        getDesignSystemDisplayTitle(designSystem),
        getDesignSystemDisplayDescription(designSystem),
        designSystem.category || '',
      ].join(' ')
      return normalizePickerSearch(searchable).includes(query)
    })
  }, [availableDesignSystems, designSystemSearchQuery])
  const selectedSkill = useMemo(
    () => availableSkills.find((skill) => skill.id === activeSkillId) ?? null,
    [availableSkills, activeSkillId],
  )
  const selectedDesignSystem = useMemo(
    () => availableDesignSystems.find((system) => system.id === selectedDesignSystemId) ?? null,
    [availableDesignSystems, selectedDesignSystemId],
  )
  const openDesignSystemPreviewFromMenu = useCallback((designSystem: HarnessDesignSystemRead) => {
    selectDesignSystem(designSystem.id)
    setIsDesignSystemSelectOpen(false)
    setIsDesignSystemPreviewOpen(true)
  }, [selectDesignSystem])
  const openSkillExamplePreviewFromMenu = useCallback((skill: HarnessSkillRead) => {
    setSkillExamplePreviewSkill(skill)
    setIsSkillExamplePreviewOpen(true)
  }, [])
  const effectiveSkillSelectionMode = skillSelectionMode === 'manual' ? 'manual' : 'auto'
  const runtimePreviewMeta = useMemo(() => {
    const workspaceRuntimeSession = runtimeState?.workspace_runtime_session
      && typeof runtimeState.workspace_runtime_session === 'object'
      ? runtimeState.workspace_runtime_session as Record<string, any>
      : null
    const preparedWorkspace = runtimeState?.prepared_workspace
      && typeof runtimeState.prepared_workspace === 'object'
      ? runtimeState.prepared_workspace as Record<string, any>
      : null
    const artifactManifest = runtimeState?.artifact_manifest
      && typeof runtimeState.artifact_manifest === 'object'
      ? runtimeState.artifact_manifest as Record<string, any>
      : null
    const activeEntryPath = resolveRuntimePreviewPath(artifactManifest, workspaceRuntimeSession, preparedWorkspace)
    if (!activeEntryPath && !runtimeState) {
      return null
    }
    const normalizedPreviewPath = String(previewingWorkspaceFile?.path || '').replace(/\\/g, '/')
    if (normalizedPreviewPath && activeEntryPath) {
      const sameEntry = normalizedPreviewPath === activeEntryPath
        || normalizedPreviewPath === `project/${activeEntryPath}`
      if (!sameEntry) {
        return null
      }
    }
    const strategy = String(preparedWorkspace?.strategy || runtimeState?.runtime_contract?.execution_strategy || '').trim()
    const selectedTemplate = String(preparedWorkspace?.selected_template || '').trim()
    const entryFile = String(preparedWorkspace?.entry_file || activeEntryPath.split('/').pop() || '').trim()
    const discoveryStatus = String(runtimeState?.discovery_status || '').trim()
    const direction = String(
      workspaceRuntimeSession?.selected_direction
      || (runtimeState?.runtime_contract as Record<string, any> | null)?.direction_id
      || '',
    ).trim()
    const phase = String(runtimeState?.phase || '').trim()
    const items: Array<{ label: string; value: string }> = []
    if (phase) {
      items.push({
        label: t('home.runtime.phase', 'Phase'),
        value: t(`home.runtime.phaseValue.${phase}`, phase),
      })
    }
    if (discoveryStatus) {
      items.push({
        label: t('home.runtime.discoveryStatus', 'Discovery'),
        value: t(`home.runtime.status.${discoveryStatus}`, discoveryStatus),
      })
    }
    if (strategy) {
      items.push({
        label: t('home.runtime.strategy', 'Strategy'),
        value: strategy,
      })
    }
    if (selectedTemplate) {
      items.push({
        label: t('home.runtime.template', 'Template'),
        value: selectedTemplate,
      })
    }
    if (direction) {
      items.push({
        label: t('home.runtime.direction', 'Direction'),
        value: direction,
      })
    }
    if (entryFile) {
      items.push({
        label: t('home.runtime.entryFile', 'Entry'),
        value: entryFile,
      })
    }
    if (!items.length) {
      return null
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        {items.map((item) => (
          <span
            key={`${item.label}:${item.value}`}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5',
              'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground',
            )}
          >
            <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--app-foreground-subtle)]">{item.label}</span>
            <span className="truncate max-w-[180px]">{item.value}</span>
          </span>
        ))}
      </div>
    )
  }, [isDark, previewingWorkspaceFile?.path, runtimeState, t])
  const artifactManifestMeta = useMemo(() => {
    const manifest = runtimeState?.artifact_manifest
    if (!manifest || typeof manifest !== 'object') {
      return null
    }
    const title = String(manifest.title || '').trim()
    const kind = String(manifest.kind || '').trim()
    const entry = String(manifest.entry || '').trim()
    const publication = manifest.publication && typeof manifest.publication === 'object'
      ? manifest.publication as Record<string, any>
      : null
    const publicationPayload = publication?.payload && typeof publication.payload === 'object'
      ? publication.payload as Record<string, any>
      : null
    const manifestRecord = manifest as Record<string, any>
    const openDesignLint = (
      publicationPayload?.open_design_lint && typeof publicationPayload.open_design_lint === 'object'
        ? publicationPayload.open_design_lint
        : manifestRecord.open_design_lint && typeof manifestRecord.open_design_lint === 'object'
          ? manifestRecord.open_design_lint
          : null
    ) as Record<string, any> | null
    const lintFindings = Array.isArray(openDesignLint?.findings)
      ? openDesignLint.findings as Array<Record<string, any>>
      : []
    const lintWarnings = lintFindings.filter((finding) => {
      const severity = String(finding?.severity || '').toUpperCase()
      return severity === 'P1' || severity === 'P2'
    })
    const p1Count = Number(openDesignLint?.p1_count || 0)
    const p2Count = Number(openDesignLint?.p2_count || 0)
    const published = Boolean(publication?.published_file_id || publication?.version_id || publication?.path)
    const items: Array<{ label: string; value: string }> = []
    if (title) {
      items.push({ label: t('home.runtime.artifactTitle', 'Artifact'), value: title })
    }
    if (kind) {
      items.push({ label: t('home.runtime.artifactKind', 'Kind'), value: kind })
    }
    if (entry) {
      items.push({ label: t('home.runtime.artifactEntry', 'Entry'), value: entry })
    }
    items.push({
      label: t('home.runtime.artifactPublishStatus', 'Publish'),
      value: published
        ? t('home.runtime.artifactPublished', 'Published')
        : t('home.runtime.artifactRegistered', 'Registered'),
    })
    return (
      <div className={cn(
        'w-full max-w-4xl mx-auto px-8 pt-4',
        isDark ? 'text-zinc-200' : 'text-zinc-700',
      )}>
        <div className={cn(
          'rounded-2xl border px-4 py-3 text-xs',
          'border-[var(--app-border)] bg-[var(--app-surface-muted)]',
        )}>
          <div className="flex flex-wrap items-center gap-2">
            {items.map((item) => (
              <span
                key={`${item.label}:${item.value}`}
                className={cn(
                  'inline-flex min-w-0 items-center gap-1 rounded-full border px-2 py-0.5',
                  'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground',
                )}
              >
                <span className="shrink-0 text-[10px] uppercase tracking-[0.08em] text-[var(--app-foreground-subtle)]">{item.label}</span>
                <span className="max-w-[260px] truncate">{item.value}</span>
              </span>
            ))}
          </div>
          {lintWarnings.length > 0 || p1Count > 0 || p2Count > 0 ? (
            <div className={cn(
              'mt-3 rounded-xl border px-3 py-2 text-xs',
              isDark ? 'border-amber-300/20 bg-amber-300/10 text-amber-100' : 'border-amber-200 bg-amber-50 text-amber-900',
            )}>
              <div className="font-medium">
                <span>{t('home.runtime.openDesignLintWarnings', 'P1/P2 lint warnings')}</span>
                <span>{' · '}</span>
                <span>{t('home.runtime.openDesignLintCounts', `${p1Count} P1, ${p2Count} P2`, { p1: p1Count, p2: p2Count })}</span>
              </div>
              {lintWarnings.length > 0 ? (
                <ul className="mt-1 space-y-0.5">
                  {lintWarnings.slice(0, 4).map((finding, index) => (
                    <li key={`${finding.id || index}:${finding.message || ''}`} className="line-clamp-2">
                      [{String(finding.severity || '').toUpperCase()}] {String(finding.id || 'lint')} - {String(finding.message || '')}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    )
  }, [isDark, runtimeState?.artifact_manifest, t])
  const applyArtifactMode = useCallback((modeId: HomeArtifactMode) => {
    if (typeof setArtifactMode === 'function') {
      setArtifactMode(modeId)
    }
  }, [setArtifactMode])
  useEffect(() => {
    const latestPreviewFile = findUpdatedPreviewFile(previewingWorkspaceFile, workspaceFiles)
    if (!latestPreviewFile || latestPreviewFile === previewingWorkspaceFile) {
      return
    }

    setPreviewingWorkspaceFile(latestPreviewFile as SessionFileItem)
    if (shouldResetPreviewVersionSelection(previewingWorkspaceFile, latestPreviewFile, previewingVersionId)) {
      setPreviewingVersionId(null)
      setPreviewingOfficeSession(null)
    }
  }, [previewingVersionId, previewingWorkspaceFile, workspaceFiles])

  useEffect(() => {
    const runtimeEntryPath = resolveRuntimePreviewPath(
      runtimeState?.artifact_manifest && typeof runtimeState.artifact_manifest === 'object'
        ? runtimeState.artifact_manifest as Record<string, any>
        : null,
      runtimeState?.workspace_runtime_session && typeof runtimeState.workspace_runtime_session === 'object'
        ? runtimeState.workspace_runtime_session as Record<string, any>
        : null,
      runtimeState?.prepared_workspace && typeof runtimeState.prepared_workspace === 'object'
        ? runtimeState.prepared_workspace as Record<string, any>
        : null,
    )
    if (!runtimeEntryPath || previewingWorkspaceFile) {
      return
    }
    const runtimePreviewFile = findRuntimePreviewFile(runtimeEntryPath, workspaceFiles)
    if (!runtimePreviewFile) {
      return
    }
    setPreviewingWorkspaceFile(runtimePreviewFile as SessionFileItem)
    setPreviewingVersionId(null)
    setPreviewingOfficeSession(null)
    setWorkspaceFilePreviewError(null)
  }, [previewingWorkspaceFile, runtimeState, workspaceFiles])

  useEffect(() => {
    loadConversations(0 /* unused for harness */)
  }, [loadConversations])

  useEffect(() => {
    void loadUiConfig()
  }, [loadUiConfig])

  useEffect(() => {
    let isMounted = true

    const loadSkillMetadata = async () => {
      try {
        const { skills, designSystems } = await loadHomeHarnessMetadata()
        if (!isMounted) {
          return
        }
        setAvailableSkills(filterHomeVisibleSkills(skills))
        setAvailableDesignSystems(designSystems)
      } catch (error) {
        console.error('Failed to load harness metadata', error)
      }
    }

    void loadSkillMetadata()

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    setActiveMode(artifactMode)
  }, [artifactMode])

  useEffect(() => {
    if (!supportsDesignSystem(activeMode) && selectedDesignSystemId) {
      selectDesignSystem(null)
    }
  }, [activeMode, selectDesignSystem, selectedDesignSystemId])

  useEffect(() => {
    if (forwardTransferHydratedRef.current) {
      return
    }
    forwardTransferHydratedRef.current = true

    const searchParams = new URLSearchParams(window.location.search)
    const transferKey = searchParams.get('forwardTransferKey')
    if (!transferKey) {
      return
    }

    const payload = loadHomeForwardTransfer(transferKey)
    if (!payload) {
      deleteHomeForwardTransfer(transferKey)
      searchParams.delete('forwardTransferKey')
      const nextSearch = searchParams.toString()
      window.history.replaceState({}, '', `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash}`)
      return
    }

    setInputValue(payload.text)
    setPendingAttachments(payload.attachments.map((attachment): AttachmentData => ({
      type: 'image',
      url: attachment.url,
      name: getAttachmentNameFromUrl(attachment.url),
      reference: attachment.reference,
    })))
    const nextMode = normalizeHomeArtifactMode(payload.mode)
    setActiveMode(nextMode)
    applyArtifactMode(nextMode)
    activateSkill(null)
    deleteHomeForwardTransfer(transferKey)
    searchParams.delete('forwardTransferKey')
    const nextSearch = searchParams.toString()
    window.history.replaceState({}, '', `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash}`)
  }, [activateSkill, applyArtifactMode])

  const handleModeChange = useCallback((modeId: HomeArtifactMode) => {
    setActiveMode(modeId)
    applyArtifactMode(modeId)
    activateSkill(null)
  }, [activateSkill, applyArtifactMode])

  const ensureHomeModelPreferences = useCallback(async () => {
    if (
      homeModelPreferences.image_model &&
      homeModelPreferences.video_model &&
      homeModelPreferences.multimodal_model
    ) {
      return homeModelPreferences
    }

    const catalogs = await loadHomepageModelCatalog(i18n.language, { appName, appNameEn })
    setHomeAvailableImageModels(catalogs.imageModels)
    setHomeAvailableMultimodalModels(catalogs.multimodalModels)
    const nextPreferences = fillHomepageDefaultModelPreferences(
      homeModelPreferences,
      catalogs,
      homeThinkingEnabled,
    )

    setHomeModelPreferences(nextPreferences)
    return nextPreferences
  }, [appName, appNameEn, homeModelPreferences, homeThinkingEnabled, i18n.language])

  const homeThinkingModeAvailable = isHomepageThinkingModeAvailableForModel(
    homeAvailableMultimodalModels,
    {
      value: homeModelPreferences.multimodal_model,
      provider: homeModelPreferences.multimodal_provider,
    },
  )
  const currentHomeImageModel = homeAvailableImageModels.find(model => (
    model.value === homeModelPreferences.image_model
    && model.provider === homeModelPreferences.image_provider
  ))
  const maxEcommerceReferenceImages = currentHomeImageModel?.maxReferenceImages

  const handleHomeThinkingChange = useCallback((enabled: boolean) => {
    if (enabled === homeThinkingEnabled) return
    if (enabled && !homeThinkingModeAvailable) return

    const nextModel = getHomepageModeSwitchTargetMultimodalModel(
      homeAvailableMultimodalModels,
      homeThinkingEnabled,
      enabled,
      {
        value: homeModelPreferences.multimodal_model,
        provider: homeModelPreferences.multimodal_provider,
      },
    )

    if (nextModel) {
      setHomeModelPreferences((current) => ({
        ...current,
        multimodal_model: nextModel.value,
        multimodal_provider: nextModel.provider,
      }))
    }

    setHomeThinkingEnabled(enabled)
  }, [
    homeAvailableMultimodalModels,
    homeModelPreferences.multimodal_model,
    homeModelPreferences.multimodal_provider,
    homeThinkingEnabled,
    homeThinkingModeAvailable,
  ])

  const resetLocalConversationUi = useCallback(() => {
    setInputValue('')
    setPendingAttachments((current) => {
      revokeAttachmentBlobUrls(current)
      return []
    })
    setIsComposerExpanded(false)
    setIsDragActive(false)
    dragDepthRef.current = 0
    setActiveFileTab('all')
    setIsFilesModalOpen(false)
    setPreviewingWorkspaceFile(null)
    setPreviewingVersionId(null)
    setPreviewingWorkspaceFileContent('')
    setPreviewingWorkspaceHtmlUrl(undefined)
    setPreviewingOfficeSession(null)
    setIsOfficeSessionLoading(false)
    setWorkspaceFilePreviewError(null)
    setIsWorkspaceFilePreviewLoading(false)
    setSubmittingInteractionLabels({})
  }, [])

  const handleRespondToUserInteraction = useCallback(async (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
  ) => {
    const nextLabel = String(displayLabel || answer || '').trim() || answer
    setSubmittingInteractionLabels((current) => ({
      ...current,
      [requestId]: nextLabel,
    }))
    try {
      await respondToAgent(requestId, answer, displayLabel, approved, answers)
    } finally {
      setSubmittingInteractionLabels((current) => {
        const next = { ...current }
        delete next[requestId]
        return next
      })
    }
  }, [respondToAgent])

  const isPlanningReady = activeConversation?.phase === 'planning_ready'
  const isRevisingPlan = activeConversation?.phase === 'revising_plan'
  const isAgentBusy = isStreaming || runStatus === 'running'
  const isPlanReviewComposerLocked = isPlanningReady || isRevisingPlan
  const isPrimaryComposerLocked = isPlanReviewComposerLocked || isAgentBusy

  const ensureBalanceForModelPreferences = useCallback((preferences: { multimodal_provider?: string } | null | undefined) => {
    if (!isBalanceRequiredForMultimodalProvider(preferences?.multimodal_provider)) {
      return true
    }
    return ensureBalanceOrNotify(user?.balance_cents, t)
  }, [t, user?.balance_cents])

  const handleStartExecution = useCallback(async () => {
    const effectiveModelPreferences = await ensureHomeModelPreferences()
    if (!ensureBalanceForModelPreferences(effectiveModelPreferences)) return
    await startExecution()
  }, [ensureBalanceForModelPreferences, ensureHomeModelPreferences, startExecution])

  const handleRevisePlan = useCallback(async (instruction: string) => {
    await revisePlan(instruction)
  }, [revisePlan])

  const handlePatchCurrentOutline = useCallback(async (plan: UserPlanRead) => {
    await patchCurrentOutline(plan)
  }, [patchCurrentOutline])

  const submitHomepageMessage = useCallback(async (
    text: string,
    options?: {
      attachments?: AttachmentData[]
      actionType?: string | null
      modelPreferences?: typeof homeModelPreferences
    },
  ) => {
    if (!text.trim() || isStreaming || isPrimaryComposerLocked) return

    const effectiveModelPreferences = options?.modelPreferences || await ensureHomeModelPreferences()
    if (!ensureBalanceForModelPreferences(effectiveModelPreferences)) return

    setMode(homeThinkingEnabled ? 'plan' : 'fast')
    setModelPreferences(effectiveModelPreferences)

    // Auto-create harness conversation if needed
    if (!conversationId) {
      await createHarnessConversation(activeSkillId || undefined, {
        modelPreferences: effectiveModelPreferences,
        artifactMode: activeMode,
      })
    }

    // Upload deferred local files now that conversation exists
    let attachments: AttachmentData[] | undefined = options?.attachments
    if (attachments === undefined) {
      attachments = pendingAttachments.length > 0 ? [...pendingAttachments] : undefined
      setPendingAttachments((current) => {
        revokeAttachmentBlobUrls(current)
        return []
      })
    }

    if (attachments?.some(a => a._localFile)) {
      const convId = useChatStore.getState().conversationId
      if (convId) {
        const uploaded: AttachmentData[] = []
        for (const att of attachments) {
          if (att._localFile) {
            if (!validateUploadFileSize(att._localFile, 'harness_attachment_max_bytes', t)) {
              continue
            }
            try {
              const response = await agentApi.uploadHarnessAttachment(String(convId), att._localFile)
              upsertWorkspaceFile?.(convId, buildWorkspaceFileFromHarnessUpload(
                response.data,
                att.name,
              ))
              uploaded.push({
                type: response.data.type === 'image' ? 'image' : 'file',
                url: response.data.url,
                name: response.data.filename || att.name,
              })
            } catch {
              toast.error(`Failed to upload ${att.name}`)
            }
          } else {
            uploaded.push(att)
          }
        }
        attachments = uploaded.length > 0 ? uploaded : undefined
      }
    }

    const activeBaseFileVersion = getActivePreviewBaseFileVersion(
      previewingWorkspaceFile,
      previewingVersionId,
    )

    await sendMessage(text, attachments, {
      modelPreferences: effectiveModelPreferences,
      baseFileVersions: activeBaseFileVersion ? [activeBaseFileVersion] : null,
      actionType: options?.actionType ?? null,
    })
  }, [
    isStreaming,
    conversationId,
    activeMode,
    homeThinkingEnabled,
    ensureHomeModelPreferences,
    pendingAttachments,
    activeSkillId,
    createHarnessConversation,
    sendMessage,
    upsertWorkspaceFile,
    isPrimaryComposerLocked,
    setMode,
    setModelPreferences,
    previewingWorkspaceFile,
    previewingVersionId,
    ensureBalanceForModelPreferences,
  ])

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isStreaming || isPrimaryComposerLocked) return
    const effectiveModelPreferences = await ensureHomeModelPreferences()
    if (!ensureBalanceForModelPreferences(effectiveModelPreferences)) return

    const text = inputValue
    setInputValue('')
    await submitHomepageMessage(text, { modelPreferences: effectiveModelPreferences })
  }, [
    ensureBalanceForModelPreferences,
    ensureHomeModelPreferences,
    inputValue,
    isPrimaryComposerLocked,
    isStreaming,
    submitHomepageMessage,
  ])

  const handlePresentationRegenerateSlide = useCallback(async (slideIndex: number) => {
    await submitHomepageMessage(
      t('home.ppt.regenerate_prompt', {
        defaultValue: 'Help me regenerate slide {{page}} in the PPT',
        page: slideIndex,
      }),
      {
        attachments: undefined,
        actionType: 'presentation_regenerate_slide',
      },
    )
  }, [submitHomepageMessage, t])

  const isInteractionSubmitting = Object.keys(submittingInteractionLabels).length > 0

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (isPrimaryComposerLocked) {
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend, isPrimaryComposerLocked])

  const handleNewChat = useCallback(() => {
    newChat()
    resetLocalConversationUi()
    setActiveMode('web')
    applyArtifactMode('web')
    activateSkill(null)
  }, [activateSkill, applyArtifactMode, newChat, resetLocalConversationUi])

  const handleLoadConversation = useCallback((id: number | string) => {
    resetLocalConversationUi()
    loadConversation(id)
  }, [loadConversation, resetLocalConversationUi])

  const handleDownloadFile = useCallback(async (file: WorkspaceFileRead) => {
    if (!conversationId) {
      return
    }

    const selectedVersionId = previewingWorkspaceFile?.file_id === file.file_id
      ? previewingVersionId || file.current_version_id
      : file.current_version_id
    const blob = file.file_id && selectedVersionId
      ? await agentApi.fetchWorkspaceFileVersionBlob(String(conversationId), file.file_id, selectedVersionId)
      : await agentApi.fetchWorkspaceFileBlob(
        String(conversationId),
        isHarnessWorkspaceRelativePath(file.path)
          ? normalizeHarnessWorkspacePath(file.path)
          : file.path,
      )

    downloadWorkspaceBlob(blob, file.name)
  }, [conversationId, previewingVersionId, previewingWorkspaceFile])

  const handleOpenExternalPreviewFile = useCallback(async (file: WorkspaceFileRead, suite: ExternalOpenSuite) => {
    if (!conversationId || !isExternalOpenSupported(file)) {
      return
    }

    setIsOpeningExternalPreview(true)
    try {
      const selectedVersionId = previewingWorkspaceFile?.file_id === file.file_id
        ? previewingVersionId || file.current_version_id
        : file.current_version_id
      const { preview_token } = await agentApi.createWorkspacePreviewToken(String(conversationId))
      const accessibleUrl = isSessionHtmlFile(file)
        ? file.file_id && selectedVersionId
          ? agentApi.getWorkspaceHtmlVersionPreviewUrl(
            String(conversationId),
            file.file_id,
            selectedVersionId,
            preview_token,
          )
          : agentApi.getWorkspaceHtmlPreviewUrl(
            String(conversationId),
            normalizeHarnessWorkspacePath(file.path),
            preview_token,
          )
        : file.file_id && selectedVersionId
          ? agentApi.getWorkspacePreviewFileVersionUrl(
            String(conversationId),
            file.file_id,
            selectedVersionId,
            preview_token,
            file.name || file.path,
          )
          : agentApi.getWorkspacePreviewFileUrl(
            String(conversationId),
            normalizeHarnessWorkspacePath(file.path),
            preview_token,
          )

      const didOpen = await openExternalTarget(buildExternalOpenTarget(file, accessibleUrl, suite))
      if (!didOpen) {
        toast.error(t('home.chat.open_external_unsupported'))
      }
    } catch (error) {
      console.error('Failed to open file externally:', error)
      toast.error(t('home.chat.open_external_failed'))
    } finally {
      setIsOpeningExternalPreview(false)
    }
  }, [conversationId, previewingVersionId, previewingWorkspaceFile, t])

  const handlePreviewWorkspaceFile = useCallback(async (file: WorkspaceFileRead) => {
    if (previewingOfficeSession?.session_id && conversationId) {
      await agentApi.closeWorkspaceOfficeSession(String(conversationId), {
        session_id: previewingOfficeSession.session_id,
      }).catch(() => undefined)
    }
    setIsFilesModalOpen(false)
    setWorkspaceFilePreviewError(null)
    setPreviewingWorkspaceFile(file as SessionFileItem)
    setPreviewingVersionId(null)
    setPreviewingOfficeSession(null)
  }, [conversationId, previewingOfficeSession])

  const handleCloseWorkspaceFilePreview = useCallback(async () => {
    if (previewingOfficeSession?.session_id && conversationId) {
      await agentApi.closeWorkspaceOfficeSession(String(conversationId), {
        session_id: previewingOfficeSession.session_id,
      }).catch(() => undefined)
    }
    setPreviewingWorkspaceFile(null)
    setPreviewingVersionId(null)
    setPreviewingWorkspaceFileContent('')
    setPreviewingWorkspaceHtmlUrl(undefined)
    setPreviewingOfficeSession(null)
    setIsOfficeSessionLoading(false)
    setWorkspaceFilePreviewError(null)
    setIsWorkspaceFilePreviewLoading(false)
  }, [conversationId, previewingOfficeSession])

  const handleOpenWorkspaceRelativeFile = useCallback((filePath: string, fileName?: string) => {
    const normalizedPath = normalizeHarnessWorkspacePath(filePath)
    if (!normalizedPath) {
      return
    }
    const currentSessionFiles = collectSessionFiles(workspaceFiles)
    const matchedFile = currentSessionFiles.find((file) => normalizeHarnessWorkspacePath(file.path) === normalizedPath)
    if (matchedFile) {
      void handlePreviewWorkspaceFile(matchedFile)
      return
    }

    setWorkspaceFilePreviewError(null)
    setPreviewingWorkspaceFile({
      file_id: normalizedPath,
      name: fileName || normalizedPath.split('/').pop() || normalizedPath,
      path: normalizedPath,
      type: inferWorkspaceFileTypeFromPath(normalizedPath),
      size: 0,
      created_at: new Date().toISOString(),
      current_version_id: '',
      versions: [],
      source: 'workspace',
    })
  }, [handlePreviewWorkspaceFile, workspaceFiles])

  const handleSelectPreviewVersion = useCallback(async (versionId: string) => {
    if (previewingOfficeSession?.session_id && conversationId) {
      await agentApi.closeWorkspaceOfficeSession(String(conversationId), {
        session_id: previewingOfficeSession.session_id,
      }).catch(() => undefined)
    }
    setPreviewingVersionId(versionId)
    setPreviewingOfficeSession(null)
  }, [conversationId, previewingOfficeSession])

  const handleHomePreferencesChange = useCallback((prefs: Partial<ModelPreferences>) => {
    setHomeModelPreferences((current) => ({ ...current, ...prefs }))
    setModelPreferences(prefs)
  }, [setModelPreferences])

  const showUnsupportedUploadToast = useCallback(() => {
    toast.error(t('home.chat.upload_unsupported_format'))
  }, [t])

  const handleAttachmentRemove = useCallback((index: number) => {
    setPendingAttachments((current) => current.filter((_, currentIndex) => currentIndex !== index))
  }, [])

  const handleLibraryAssetsSelected = useCallback((assets: HomeChatLibraryAsset[]) => {
    if (ecommerceReferenceImageSelect) {
      ecommerceReferenceImageSelect.onSelect(
        assets
          .filter((asset) => asset.type === 'image')
          .map((asset) => asset.url)
          .filter(Boolean),
      )
      setEcommerceReferenceImageSelect(null)
      return
    }
    setPendingAttachments((current) => [
      ...current,
      ...assets.map((asset): AttachmentData => ({
        type: asset.type === 'video' ? 'file' : 'image',
        url: asset.url,
        preview_url: asset.type === 'image' ? asset.list_preview_url || asset.url : undefined,
        name: asset.name || getAttachmentNameFromUrl(asset.url),
      })),
    ])
  }, [ecommerceReferenceImageSelect])

  const handleReferenceGalleryImagesSelected = useCallback((assets: AssetLibrarySelectedAsset[]) => {
    if (ecommerceReferenceImageSelect) {
      ecommerceReferenceImageSelect.onSelect(assets.map((asset) => asset.url).filter(Boolean))
      setEcommerceReferenceImageSelect(null)
      return
    }
    setPendingAttachments((current) => [
      ...current,
      ...assets.map((asset): AttachmentData => ({
        type: 'image',
        url: asset.url,
        preview_url: asset.list_preview_url || asset.url,
        name: asset.name || getAttachmentNameFromUrl(asset.url),
      })),
    ])
  }, [ecommerceReferenceImageSelect])

  const handleRequestEcommerceReferenceImages = useCallback((
    source: EcommerceReferenceImageSource,
    onSelect: (urls: string[]) => void,
    options?: EcommerceReferenceImageRequestOptions,
  ) => {
    setEcommerceReferenceImageSelect({ onSelect, maxSelection: options?.maxSelection })
    if (source === 'reference_gallery') {
      setIsReferenceGalleryPickerOpen(true)
      return
    }
    setIsAssetLibraryOpen(true)
  }, [])

  const handleUploadEcommerceReferenceImage = useCallback(async (file: File): Promise<string | null> => {
    if (!validateUploadFileSize(file, 'harness_attachment_max_bytes', t)) {
      return null
    }
    let currentConversationId = conversationId
    if (!currentConversationId) {
      const effectiveModelPreferences = await ensureHomeModelPreferences()
      await createHarnessConversation(activeSkillId || undefined, {
        modelPreferences: effectiveModelPreferences,
        artifactMode: activeMode,
      })
      currentConversationId = useChatStore.getState().conversationId
    }
    if (!currentConversationId) {
      toast.error(t('home.chat.upload_failed', 'Upload failed'))
      return null
    }
    const response = await agentApi.uploadHarnessAttachment(String(currentConversationId), file)
    upsertWorkspaceFile?.(currentConversationId, buildWorkspaceFileFromHarnessUpload(
      response.data,
      file.name,
    ))
    return response.data.url || null
  }, [
    activeMode,
    activeSkillId,
    conversationId,
    createHarnessConversation,
    ensureHomeModelPreferences,
    t,
    upsertWorkspaceFile,
  ])

  const handleUseGeneratedAsReference = useCallback((attachment: AttachmentData) => {
    setPendingAttachments((current) => [...current, attachment])
  }, [])

  const appendLocalFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return

    const { supported, unsupported } = filterSupportedHomeHarnessAttachmentFiles(files)
    if (unsupported.length > 0) {
      showUnsupportedUploadToast()
    }
    if (supported.length === 0) {
      return
    }

    const currentConversationId = conversationId
    if (currentConversationId) {
      const nextAttachments: AttachmentData[] = []
      for (const file of supported) {
        if (!validateUploadFileSize(file, 'harness_attachment_max_bytes', t)) {
          continue
        }
        try {
          const response = await agentApi.uploadHarnessAttachment(String(currentConversationId), file)
          upsertWorkspaceFile?.(currentConversationId, buildWorkspaceFileFromHarnessUpload(
            response.data,
            file.name,
          ))
          const isUploadedImage = response.data.type === 'image'
          const previewUrl = isUploadedImage
            ? await resolveUploadedImageAttachmentPreviewUrl(currentConversationId, response.data.url)
            : undefined
          nextAttachments.push({
            type: isUploadedImage ? 'image' : 'file',
            url: response.data.url,
            preview_url: previewUrl,
            name: response.data.filename || file.name,
          })
        } catch {
          toast.error(`Failed to upload ${file.name}`)
        }
      }
      setPendingAttachments((current) => [...current, ...nextAttachments])
      return
    }

    const nextAttachments: AttachmentData[] = []
    for (const file of supported) {
      if (!validateUploadFileSize(file, 'harness_attachment_max_bytes', t)) {
        continue
      }
      const fileKind = inferHomeHarnessAttachmentKind(file)
      nextAttachments.push({
        type: fileKind === 'image' ? 'image' : 'file',
        url: '',
        name: file.name,
        _localFile: file,
        _clientAttachmentId: createPendingAttachmentId(),
      })
    }
    setPendingAttachments((current) => [...current, ...nextAttachments])
    for (const [index, attachment] of nextAttachments.entries()) {
      const file = supported[index]
      if (!file || attachment.type !== 'image' || !attachment._clientAttachmentId) {
        continue
      }
      void enqueueLocalImageThumbnail(file).then((preview) => {
        if (!preview.preview_url) {
          return
        }
        let applied = false
        setPendingAttachments((current) => current.map((currentAttachment) => {
          if (currentAttachment._clientAttachmentId !== attachment._clientAttachmentId) {
            return currentAttachment
          }
          applied = true
          return { ...currentAttachment, ...preview }
        }))
        if (!applied) {
          revokeAttachmentBlobUrls([{ type: 'image', url: '', ...preview }])
        }
      })
    }
  }, [conversationId, showUnsupportedUploadToast, t])

  const handleLocalFilesSelected = useCallback(async (files: FileList | null) => {
    if (isPrimaryComposerLocked) return
    if (!files || files.length === 0) return
    await appendLocalFiles(Array.from(files))
  }, [appendLocalFiles, isPrimaryComposerLocked])

  const handleComposerPaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (isPrimaryComposerLocked) {
      e.preventDefault()
      return
    }
    const clipboardItems = Array.from(e.clipboardData?.items || [])
    const pastedFiles = clipboardItems
      .filter((item) => item.kind === 'file')
      .map((item) => item.getAsFile())
      .filter((file): file is File => !!file)

    if (pastedFiles.length === 0) {
      return
    }

    e.preventDefault()
    await appendLocalFiles(pastedFiles)
  }, [appendLocalFiles, isPrimaryComposerLocked])

  const handleComposerDragEnter = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (isPrimaryComposerLocked) {
      return
    }
    const hasFiles = Array.from(e.dataTransfer?.items || []).some((item) => item.kind === 'file')
    if (!hasFiles) {
      return
    }
    e.preventDefault()
    dragDepthRef.current += 1
    setIsDragActive(true)
  }, [isPrimaryComposerLocked])

  const handleComposerDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (isPrimaryComposerLocked) {
      return
    }
    const hasFiles = Array.from(e.dataTransfer?.items || []).some((item) => item.kind === 'file')
    if (!hasFiles) {
      return
    }
    e.preventDefault()
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy'
    }
    setIsDragActive(true)
  }, [isPrimaryComposerLocked])

  const handleComposerDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (isPrimaryComposerLocked) {
      return
    }
    const hasFiles = Array.from(e.dataTransfer?.items || []).some((item) => item.kind === 'file')
    if (!hasFiles) {
      return
    }
    e.preventDefault()
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) {
      setIsDragActive(false)
    }
  }, [isPrimaryComposerLocked])

  const handleComposerDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    if (isPrimaryComposerLocked) {
      e.preventDefault()
      return
    }
    const droppedFiles = Array.from(e.dataTransfer?.files || [])
    if (droppedFiles.length === 0) {
      return
    }
    e.preventDefault()
    dragDepthRef.current = 0
    setIsDragActive(false)
    await appendLocalFiles(droppedFiles)
  }, [appendLocalFiles, isPrimaryComposerLocked])

  const hasConversationContent = messages.length > 0 || streamingBlocks.length > 0 || isStreaming || !!userInteraction
  const sessionFiles = useMemo(
    () => collectSessionFiles(workspaceFiles),
    [workspaceFiles],
  )
  const fileTabCounts = useMemo(
    () => getFileTabCounts(sessionFiles),
    [sessionFiles],
  )
  const visibleSessionFiles = useMemo(
    () => filterFilesByTab(sessionFiles, activeFileTab),
    [activeFileTab, sessionFiles],
  )
  const isMarkdownPreviewOpen = !!previewingWorkspaceFile && isSessionMarkdownFile(previewingWorkspaceFile)
  const isHtmlPreviewOpen = !!previewingWorkspaceFile && isSessionHtmlFile(previewingWorkspaceFile)
  const isOfficeDocPreviewOpen = !!previewingWorkspaceFile && isSessionOfficeDocFile(previewingWorkspaceFile)
  const isOfficeSheetPreviewOpen = !!previewingWorkspaceFile && isSessionOfficeSheetFile(previewingWorkspaceFile)
  const isPresentationPreviewOpen = !!previewingWorkspaceFile && isSessionPresentationFile(previewingWorkspaceFile)
  const isTextPreviewOpen = !!previewingWorkspaceFile && isSessionTextLikeFile(previewingWorkspaceFile)
  const isRailPreviewOpen = isMarkdownPreviewOpen
    || isHtmlPreviewOpen
    || isOfficeDocPreviewOpen
    || isOfficeSheetPreviewOpen
    || isPresentationPreviewOpen
    || isTextPreviewOpen
  const previewMediaPath = previewingWorkspaceFile && !isRailPreviewOpen
    ? previewingWorkspaceFile.path
    : undefined
  const activePreviewBaseFileVersion = useMemo(
    () => getActivePreviewBaseFileVersion(previewingWorkspaceFile, previewingVersionId),
    [previewingWorkspaceFile, previewingVersionId],
  )
  const activePreviewVersionLabel = useMemo(() => {
    if (!previewingWorkspaceFile || !activePreviewBaseFileVersion) {
      return ''
    }
    const versions = previewingWorkspaceFile.versions || []
    const versionIndex = versions.findIndex((version) => version.version_id === activePreviewBaseFileVersion.version_id)
    return versionIndex >= 0
      ? t('homeHarness.fileVersions.versionLabel', { number: versionIndex + 1 })
      : activePreviewBaseFileVersion.version_id
  }, [activePreviewBaseFileVersion, previewingWorkspaceFile, t])
  const previewingWorkspaceFileUrl = useHarnessMediaSource(
    conversationId,
    previewMediaPath,
  )

  useEffect(() => {
    if (
      !previewingWorkspaceFile
      || (!isSessionMarkdownFile(previewingWorkspaceFile) && !isSessionTextLikeFile(previewingWorkspaceFile))
      || !conversationId
    ) {
      setPreviewingWorkspaceFileContent('')
      setWorkspaceFilePreviewError(null)
      setIsWorkspaceFilePreviewLoading(false)
      return
    }

    let cancelled = false
    setIsWorkspaceFilePreviewLoading(true)
    setWorkspaceFilePreviewError(null)
    const versionId = previewingVersionId || previewingWorkspaceFile.current_version_id
    const blobPromise = previewingWorkspaceFile.file_id && versionId
      ? agentApi.fetchWorkspaceFileVersionBlob(String(conversationId), previewingWorkspaceFile.file_id, versionId)
      : agentApi.fetchWorkspaceFileBlob(
        String(conversationId),
        normalizeHarnessWorkspacePath(previewingWorkspaceFile.path),
      )
    blobPromise
      .then((blob) => blob.text())
      .then((text) => {
        if (!cancelled) {
          setPreviewingWorkspaceFileContent(text)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setWorkspaceFilePreviewError('Failed to load file preview.')
          setPreviewingWorkspaceFileContent('')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsWorkspaceFilePreviewLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [conversationId, previewingWorkspaceFile, isMarkdownPreviewOpen, isTextPreviewOpen, previewingVersionId])

  useEffect(() => {
      if (!previewingWorkspaceFile || !isHtmlPreviewOpen || !conversationId) {
        setPreviewingWorkspaceHtmlUrl(undefined)
        if (!isMarkdownPreviewOpen) {
          setWorkspaceFilePreviewError(null)
        setIsWorkspaceFilePreviewLoading(false)
      }
      return
    }

    let cancelled = false
    setIsWorkspaceFilePreviewLoading(true)
    setWorkspaceFilePreviewError(null)
    setPreviewingWorkspaceHtmlUrl(undefined)

    agentApi.createWorkspacePreviewToken(String(conversationId))
      .then(({ preview_token }) => {
        if (cancelled) {
          return
        }
        const versionId = previewingVersionId || previewingWorkspaceFile.current_version_id
        const previewUrl = previewingWorkspaceFile.file_id && versionId
          ? agentApi.getWorkspaceHtmlVersionPreviewUrl(
            String(conversationId),
            previewingWorkspaceFile.file_id,
            versionId,
            preview_token,
          )
          : agentApi.getWorkspaceHtmlPreviewUrl(
            String(conversationId),
            normalizeHarnessWorkspacePath(previewingWorkspaceFile.path),
            preview_token,
          )
        setPreviewingWorkspaceHtmlUrl(previewUrl)
      })
      .catch(() => {
        if (!cancelled) {
          setWorkspaceFilePreviewError('Failed to load file preview.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsWorkspaceFilePreviewLoading(false)
        }
      })

      return () => {
        cancelled = true
      }
  }, [conversationId, isHtmlPreviewOpen, isMarkdownPreviewOpen, previewingVersionId, previewingWorkspaceFile])

  useEffect(() => {
    if (
      !previewingWorkspaceFile
      || (!isOfficeDocPreviewOpen && !isOfficeSheetPreviewOpen && !isPresentationPreviewOpen)
      || !conversationId
    ) {
      setPreviewingOfficeSession(null)
      setIsOfficeSessionLoading(false)
      return
    }

    let cancelled = false
    setIsOfficeSessionLoading(true)
    setWorkspaceFilePreviewError(null)

    agentApi.openWorkspaceOfficeSession(String(conversationId), {
      file_id: previewingWorkspaceFile.file_id,
      version_id: previewingVersionId || previewingWorkspaceFile.current_version_id,
      file_path: normalizeHarnessWorkspacePath(previewingWorkspaceFile.path),
    })
      .then(async (response) => {
        const nextSession = await buildSheetOfficeSessionSnapshot(
          response.data,
          previewingWorkspaceFile.name,
        )
        if (!cancelled) {
          setPreviewingOfficeSession(nextSession)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setWorkspaceFilePreviewError('Failed to open office preview.')
          setPreviewingOfficeSession(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsOfficeSessionLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [
    conversationId,
    isOfficeDocPreviewOpen,
    isOfficeSheetPreviewOpen,
    isPresentationPreviewOpen,
    previewingWorkspaceFile,
    previewingVersionId,
  ])

    return (
      <div className="min-h-0 h-full flex-1 p-4 lg:p-6 transition-colors duration-500 bg-transparent flex flex-col overflow-hidden">
      <div className={cn(
        'w-full flex-1 min-h-0 flex gap-4 lg:gap-6 overflow-hidden',
        isRailPreviewOpen ? 'max-w-none' : 'mx-auto max-w-7xl',
      )}>

        {/* Left History Sidebar */}
        {!isRailPreviewOpen && (
          <div className={cn(
            'relative flex h-full min-h-0 w-[280px] shrink-0 flex-col overflow-hidden rounded-[32px] border border-[var(--app-border)] bg-[var(--app-glass)] shadow-[var(--app-shadow-panel)] backdrop-blur-md'
          )}>
            <div className="p-4">
              <button
                onClick={handleNewChat}
                className={cn(
                  'flex w-full items-center justify-center gap-2 rounded-xl border border-[var(--app-border)] bg-[var(--app-control)] py-2.5 text-sm font-medium text-foreground shadow-sm transition-all hover:bg-[var(--app-control-hover)]'
                )}
              >
                <Plus className="w-4 h-4" />
                {t('canvas.chat.header.new_chat', 'New Chat')}
              </button>
            </div>
            <div className="px-5 pb-2">
              <h2 className="text-[12px] font-semibold text-[var(--app-foreground-subtle)]">
                {t('canvas.chat.header.history', 'History')}
              </h2>
            </div>
            <div
              data-testid="home-chat-history-scroll"
              className="flex-1 overflow-y-auto px-3 pb-4 space-y-1 custom-scrollbar"
              onScroll={(e) => {
                const el = e.currentTarget
                if (conversationsHasMore && el.scrollHeight - el.scrollTop - el.clientHeight < 50) {
                  loadMoreConversations()
                }
              }}
            >
              {conversations.map(conv => {
                const skillMode = getHomeSkillModePresentation(resolveConversationArtifactMode(conv))
                const ConvIcon = skillMode.icon
                const modeLabel = getConversationModeLabel(skillMode.id, (key, fallback) => t(key, fallback))
                const runtimeSummary = summarizeConversationRuntime(conv, (key, fallback) => t(key, fallback), i18n.language)
                return (
                  <button
                    key={conv.id}
                    onClick={() => handleLoadConversation(conv.id)}
                    className={cn(
                      'w-full flex items-center gap-3 rounded-2xl border text-left px-3 py-2.5 transition-all',
                      conversationId === conv.id
                        ? 'border-[var(--app-border-strong)] bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]'
                        : 'border-transparent text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground'
                    )}
                  >
                    <div className={cn(
                      'shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-colors',
                      isDark ? skillMode.bg : skillMode.bgLight,
                      skillMode.color,
                    )}
                    data-testid={`home-chat-history-mode-icon-${skillMode.id}`}>
                      <ConvIcon className="w-3.5 h-3.5" />
                    </div>
                    <div className="min-w-0 flex-1 space-y-px">
                      <div className="truncate text-[12px] font-medium leading-[1.35]">{conv.title || 'Untitled'}</div>
                      <div className={cn(
                        'flex items-center justify-between gap-3 text-[10px] leading-4 text-[var(--app-foreground-subtle)]',
                      )}>
                        <span className="min-w-0 truncate">{modeLabel}</span>
                        <span className="shrink-0 text-right">{runtimeSummary}</span>
                      </div>
                    </div>
                  </button>
                )
              })}
              {conversations.length === 0 && (
                <div className="text-center text-sm text-[var(--app-foreground-subtle)] py-8">
                  {t('canvas.chat.history.empty', 'No history yet')}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Main Chat Area */}
        <div className={cn(
          'min-h-0 rounded-[32px] overflow-hidden shadow-2xl relative border flex flex-col',
          isRailPreviewOpen ? 'w-full shrink-0 md:w-[980px] md:flex-none' : 'flex-1',
          'border-[var(--app-border)] bg-[var(--app-glass)] shadow-[var(--app-shadow-panel)] backdrop-blur-2xl'
        )}>
          {conversationId && activeConversation && terminalFailureSummary
              ? (
                <div className={cn(
                  'w-full max-w-4xl mx-auto px-8 pt-6',
                  isDark ? 'text-zinc-200' : 'text-zinc-700',
                )}>
                  <div className={cn(
                    'rounded-2xl border px-4 py-3 text-sm',
                    'border-[var(--app-border)] bg-[var(--app-surface-muted)]',
                  )}>
                    <div className={cn('truncate', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
                      {t('home.chat.recent_error_label', '最近错误：')}{terminalFailureSummary}
                    </div>
                  </div>
                </div>
              )
              : null
          }
          {artifactManifestMeta}
          {/* Messages Scrollable Area */}
          <div
            ref={setMessageScrollRef}
            data-testid="home-chat-message-scroll"
            className="flex-1 min-h-0 w-full max-w-4xl mx-auto flex flex-col px-8 pt-6 overflow-y-auto custom-scrollbar"
            onScroll={handleMessageScroll}
          >
            {hasConversationContent ? (
              <div className="w-full pb-4">
                {olderMessagesHasMore ? (
                  <div className="mb-4 flex justify-center">
                    <button
                      type="button"
                      onClick={() => void loadOlderMessagesWithAnchor()}
                      disabled={olderMessagesLoading}
                      className={cn(
                        'rounded-full border px-3 py-1.5 text-xs transition',
                        'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground shadow-sm hover:bg-[var(--app-control-hover)] disabled:text-muted-foreground/60',
                      )}
                    >
                      {olderMessagesLoading
                        ? t('home.chat.loading_older_messages', 'Loading history...')
                        : t('home.chat.load_older_messages', 'Load earlier messages')}
                    </button>
                  </div>
                ) : null}
                <HomeHarnessMessageList
                  messages={messages}
                  streamingBlocks={streamingBlocks}
                  isStreaming={isStreaming}
                  runStatus={runStatus}
                  isDark={isDark}
                  t={t}
                  language={currentLanguage}
                  conversationId={conversationId}
                  conversationLastActivityAt={activeConversation?.last_activity_at ?? null}
                  conversationRuntime={activeConversation ?? null}
                  conversationPhase={activeConversation?.phase ?? null}
                  outlineRuntime={outlineRuntime ?? null}
                  userProgress={userProgress ?? null}
                  userInteraction={userInteraction ?? null}
                  respondToAgent={handleRespondToUserInteraction}
                  onStartExecution={handleStartExecution}
                  onRevisePlan={handleRevisePlan}
                  onPatchCurrentOutline={handlePatchCurrentOutline}
                  hiddenToolCalls={uiConfig.hiddenToolCalls}
                  onOpenWorkspaceRelativeFile={handleOpenWorkspaceRelativeFile}
                  sessionFiles={sessionFiles}
                  onPreviewWorkspaceFile={handlePreviewWorkspaceFile}
                  onUseGeneratedAsReference={handleUseGeneratedAsReference}
                  onRequestEcommerceReferenceImages={handleRequestEcommerceReferenceImages}
                  onUploadEcommerceReferenceImage={handleUploadEcommerceReferenceImage}
                  maxEcommerceReferenceImages={maxEcommerceReferenceImages}
                  scrollParent={messageScrollEl}
                />
              </div>
            ) : (
              /* Empty state 鈥?Welcome screen */
              <div className="flex-1 flex flex-col items-center justify-center gap-2 py-6">
                <div className={cn(
                  'flex h-14 w-14 items-center justify-center rounded-[20px] shadow-sm',
                  'border border-[var(--app-border)] bg-[var(--app-tint-primary)] text-[var(--app-primary)]',
                )}>
                  {(() => {
                    const EmptyStateModeIcon = getHomeSkillModePresentation(displayedMode).icon
                    return <EmptyStateModeIcon className="h-7 w-7" />
                  })()}
                </div>
                <div className="max-w-xl text-center">
                  <p className={cn('text-[11px] font-semibold uppercase tracking-[0.32em]', isDark ? 'text-zinc-500' : 'text-zinc-400')}>
                    {t(`home.modes.${displayedMode}`, displayedMode)}
                  </p>
                  <p className={cn('mt-2 text-sm text-center', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
                    {t('home.primarySkill.emptyStateHint', 'You can also choose a primary skill first, then start describing your request.')}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Input Area */}
          <div className={cn('w-full max-w-4xl mx-auto flex shrink-0 flex-col items-center px-4 relative z-10 pb-8', hasConversationContent ? 'mt-4' : 'mb-[10vh]')}>
            {/* Workspace files button */}
            {hasConversationContent && sessionFiles.length > 0 && (
              <div className="absolute -top-12 left-4">
                <button
                  onClick={() => setIsFilesModalOpen(true)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors shadow-sm',
                    'border border-[var(--app-border)] bg-[var(--app-control)] text-foreground',
                  )}
                >
                  <Folder className="w-4 h-4 text-amber-500" />
                  {t('canvas.chat.header.file_list', 'Files')} ({sessionFiles.length})
                </button>
              </div>
            )}

            {/* Composer */}
            <div
              data-testid="home-chat-composer-dropzone"
              onDragEnter={handleComposerDragEnter}
              onDragOver={handleComposerDragOver}
              onDragLeave={handleComposerDragLeave}
              onDrop={handleComposerDrop}
              className={cn(
              'w-full rounded-2xl border shadow-sm transition-all focus-within:shadow-md focus-within:border-blue-500/50',
              isDragActive && (isDark
                ? 'border-blue-400 bg-blue-500/10'
                : 'border-blue-400 bg-blue-50'),
              'border-[var(--app-border)] bg-[var(--app-surface)] shadow-none focus-within:shadow-none'
              )}
            >
              <div className="relative px-4 pt-4 pb-1">
                <button
                  type="button"
                  aria-label={isComposerExpanded ? 'Collapse composer' : 'Expand composer'}
                  data-testid="home-chat-composer-expand-button"
                  onClick={() => setIsComposerExpanded((current) => !current)}
                  className={cn(
                    'absolute right-4 top-3 z-10 shrink-0 p-2 rounded-lg transition-colors border',
                    'border-transparent text-muted-foreground hover:bg-[var(--app-control-hover)]',
                  )}
                >
                  {isComposerExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                {pendingAttachments.length > 0 && (
                  <AttachmentCardStrip
                    attachments={pendingAttachments}
                    isDark={isDark}
                    onRemove={handleAttachmentRemove}
                    className="pb-3"
                    conversationId={conversationId}
                  />
                )}
                {activePreviewBaseFileVersion ? (
                  <div
                    className={cn(
                      'mb-3 flex w-fit max-w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs',
                      isDark
                        ? 'border-blue-400/20 bg-blue-500/10 text-blue-100'
                        : 'border-blue-200 bg-blue-50 text-blue-700',
                    )}
                  >
                    <History className="h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0 truncate">
                      {t('homeHarness.fileVersions.composerBaseVersion', {
                        name: activePreviewBaseFileVersion.name,
                        version: activePreviewVersionLabel || activePreviewBaseFileVersion.version_id,
                      })}
                    </span>
                    <button
                      type="button"
                      aria-label={t('homeHarness.fileVersions.clearBaseVersion')}
                      onClick={() => void handleCloseWorkspaceFilePreview()}
                      className={cn(
                        'ml-1 rounded-md p-0.5 transition-colors',
                        'hover:bg-[var(--app-control-hover)]',
                      )}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : null}
                <textarea
                  data-testid="home-chat-composer-input"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={handleComposerPaste}
                  disabled={isPrimaryComposerLocked}
                  placeholder={isPlanReviewComposerLocked
                    ? t(
                      'home.planReview.lockedComposerPlaceholder',
                      'Review or adjust the outline in the card below.',
                    )
                    : t('home.placeholder', 'Please enter your thoughts')}
                  className={cn(
                    'w-full bg-transparent resize-none pr-12 outline-none text-base transition-[min-height] duration-200',
                    isComposerExpanded ? 'min-h-[240px]' : 'min-h-[110px]',
                    isDark ? 'text-zinc-200 disabled:text-zinc-500' : 'text-zinc-800 disabled:text-zinc-400',
                  )}
                />
              </div>
              <div className="px-4 py-3 flex items-center justify-between">
                <div className="flex min-w-0 items-center gap-5">
                  <div className="flex min-w-0 items-center gap-3">
                    <div
                      className={cn(
                        'flex min-w-0 items-center overflow-hidden rounded-[15px] border shadow-[var(--app-shadow-control)]',
                        'border-[var(--app-border)] bg-[var(--app-control)]',
                      )}
                    >
                      <span
                        className={cn(
                          'shrink-0 border-r px-3 py-[9px] text-[12px] font-bold tracking-[0.04em]',
                          'border-[var(--app-border)] bg-[var(--app-surface-muted)] text-muted-foreground',
                        )}
                      >
                        {t('home.primarySkill.shortLabel', '技能:').replace(':', '')}
                      </span>
                        <Popover
                          open={isSkillSelectOpen}
                          onOpenChange={(open) => {
                            setIsSkillSelectOpen(open)
                            if (!open) {
                              setSkillSearchQuery('')
                            }
                          }}
                        >
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              role="combobox"
                              aria-expanded={isSkillSelectOpen}
                              className={cn(
                                'flex h-auto min-w-0 max-w-[220px] items-center gap-2 rounded-none border-0 bg-transparent px-3 py-[9px] text-sm font-semibold shadow-none outline-none focus-visible:ring-0',
                                isDark ? 'text-zinc-200 hover:bg-transparent' : 'text-zinc-700 hover:bg-transparent',
                              )}
                            >
                              <span
                                className={cn('truncate text-left text-sm font-medium', isDark ? 'text-zinc-200' : 'text-zinc-700')}
                                title={
                                  effectiveSkillSelectionMode === 'auto'
                                    ? (
                                      selectedSkill
                                        ? t('home.primarySkill.autoSelectedDescription', {
                                          defaultValue: 'AI is currently auto-selecting {{name}} for this request.',
                                          name: getLocalizedSkillName(selectedSkill, currentLanguage),
                                        })
                                        : (skillDecisionReason || t('home.primarySkill.autoDescription', 'Leave it unset and let AI decide the best primary skill for this mode and request.'))
                                    )
                                    : (
                                      selectedSkill
                                        ? `${getLocalizedSkillName(selectedSkill, currentLanguage)}\n${getLocalizedSkillDescription(selectedSkill, currentLanguage)}`
                                        : t('home.primarySkill.autoDescription', 'Leave it unset and let AI decide the best primary skill for this mode and request.')
                                    )
                                }
                              >
                                {effectiveSkillSelectionMode === 'auto'
                                  ? (
                                    selectedSkill
                                      ? t('home.primarySkill.autoSelectedLabel', {
                                        defaultValue: '自动选择：{{name}}',
                                        name: getLocalizedSkillName(selectedSkill, currentLanguage),
                                      })
                                      : t('home.primarySkill.autoWithHint', '不指定 - 自动决定')
                                  )
                                  : (
                                    selectedSkill
                                      ? getLocalizedSkillName(selectedSkill, currentLanguage)
                                      : t('home.primarySkill.autoWithHint', '不指定 - 自动决定')
                                  )}
                              </span>
                              <ChevronDown className="h-4 w-4 shrink-0 text-[var(--app-foreground-subtle)]" aria-hidden="true" />
                            </button>
                          </PopoverTrigger>
                          <PopoverContent
                            align="start"
                            side="top"
                            sideOffset={12}
                            className={cn(
                              'z-[2200] w-[320px] rounded-xl border p-1.5 shadow-xl',
                              'border-[var(--app-border)] bg-[var(--app-glass)] text-foreground backdrop-blur-2xl',
                            )}
                          >
                            <div className="pb-1">
                              <input
                                autoFocus
                                value={skillSearchQuery}
                                onChange={(event) => setSkillSearchQuery(event.target.value)}
                                placeholder={t('home.primarySkill.searchPlaceholder', 'Search skills')}
                                className={cn(
                                  'h-8 w-full rounded-lg border px-2.5 text-xs outline-none transition-colors',
                                  'border-[var(--app-border)] bg-[var(--app-control)] text-foreground placeholder:text-muted-foreground focus:border-[var(--app-primary)]',
                                )}
                              />
                            </div>
                            <div className="max-h-[300px] overflow-y-auto">
                              <button
                                type="button"
                                data-state={activeSkillId ? 'unchecked' : 'checked'}
                                onClick={() => {
                                  activateSkill(null)
                                  setIsSkillSelectOpen(false)
                                }}
                                className={cn(
                                  'relative flex w-full items-start rounded-lg px-2.5 py-2.5 pr-8 text-left focus:bg-blue-500/10 focus:text-current',
                                  activeSkillId ? '' : isDark ? 'bg-blue-500/15' : 'bg-blue-50',
                                )}
                              >
                                <div className="flex min-w-0 flex-col gap-1">
                                  <span className="text-sm font-semibold">
                                    {t('home.primarySkill.autoWithHint', '不指定 - 自动决定')}
                                  </span>
                                  <span className={cn('text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
                                    {t('home.primarySkill.autoDescription', 'Leave it unset and let AI decide the best primary skill for this mode and request.')}
                                  </span>
                                </div>
                                {!activeSkillId ? <Check className="absolute right-2.5 top-3 h-4 w-4" /> : null}
                              </button>
                              {filteredModeEntrySkillCandidates.map((skill) => {
                                const selected = activeSkillId === skill.id
                                return (
                                  <div
                                    key={skill.id}
                                    className={cn(
                                      'relative mt-1 rounded-lg',
                                      selected ? (isDark ? 'bg-blue-500/15' : 'bg-blue-50') : '',
                                    )}
                                  >
                                    <button
                                      type="button"
                                      data-state={selected ? 'checked' : 'unchecked'}
                                      onClick={() => {
                                        activateSkill(skill.id)
                                        setIsSkillSelectOpen(false)
                                      }}
                                      className="flex w-full items-start rounded-lg px-2.5 py-2.5 pr-14 text-left focus:bg-blue-500/10 focus:text-current"
                                    >
                                      <div className="flex min-w-0 flex-col gap-1">
                                        <span
                                          className="truncate text-sm font-semibold"
                                          title={getLocalizedSkillName(skill, currentLanguage)}
                                        >
                                          {getLocalizedSkillName(skill, currentLanguage)}
                                        </span>
                                        <span
                                          className={cn('line-clamp-2 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-500')}
                                          title={getLocalizedSkillDescription(skill, currentLanguage)}
                                        >
                                          {getLocalizedSkillDescription(skill, currentLanguage)}
                                        </span>
                                      </div>
                                      {selected ? <Check className="absolute right-2.5 top-3 h-4 w-4" /> : null}
                                    </button>
                                    {skill.has_example_html ? (
                                      <button
                                        type="button"
                                        onClick={(event) => {
                                          event.preventDefault()
                                          event.stopPropagation()
                                          openSkillExamplePreviewFromMenu(skill)
                                        }}
                                        aria-label={t('home.primarySkill.exampleAria', {
                                          defaultValue: 'Preview {{name}}',
                                          name: getLocalizedSkillName(skill, currentLanguage),
                                        })}
                                        className={cn(
                                          'absolute right-2.5 bottom-2.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors',
                                          'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
                                        )}
                                      >
                                        <Eye className="h-3 w-3" />
                                        <span>{t('home.primarySkill.exampleButton', '示例')}</span>
                                      </button>
                                    ) : null}
                                  </div>
                                )
                              })}
                            </div>
                          </PopoverContent>
                        </Popover>
                    </div>
                    {supportsDesignSystem(activeMode) ? (
                      <div
                        className={cn(
                          'flex min-w-0 items-center overflow-hidden rounded-[15px] border shadow-[var(--app-shadow-control)]',
                          'border-[var(--app-border)] bg-[var(--app-control)]',
                        )}
                      >
                        <span
                          className={cn(
                            'shrink-0 border-r px-3 py-[9px] text-[12px] font-bold tracking-[0.04em]',
                            'border-[var(--app-border)] bg-[var(--app-surface-muted)] text-muted-foreground',
                          )}
                        >
                          {t('home.designSystem.shortLabel', '设计体系:').replace(':', '')}
                        </span>
                        <div className="flex shrink-0 items-center px-2">
                          <DesignSystemSwatch designSystem={selectedDesignSystem} isDark={isDark} className="h-5 w-5 rounded-md" />
                        </div>
                        <Popover
                          open={isDesignSystemSelectOpen}
                          onOpenChange={(open) => {
                            setIsDesignSystemSelectOpen(open)
                            if (!open) {
                              setDesignSystemSearchQuery('')
                            }
                          }}
                        >
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              role="combobox"
                              aria-expanded={isDesignSystemSelectOpen}
                              className={cn(
                                'flex h-auto min-w-0 max-w-[220px] items-center gap-2 rounded-none border-0 bg-transparent px-3 py-[9px] text-sm font-semibold shadow-none outline-none focus-visible:ring-0',
                                isDark ? 'text-zinc-200 hover:bg-transparent' : 'text-zinc-700 hover:bg-transparent',
                              )}
                            >
                              <span
                                className={cn('truncate text-left text-sm font-medium', isDark ? 'text-zinc-200' : 'text-zinc-700')}
                                title={selectedDesignSystem
                                  ? `${getDesignSystemDisplayTitle(selectedDesignSystem)}\n${selectedDesignSystem.description}`
                                  : t('home.designSystem.autoDescription', 'Leave it unset and let AI recommend a design system after the quick brief.')}
                              >
                                {selectedDesignSystem
                                  ? t('home.designSystem.autoSelectedLabel', {
                                    defaultValue: '自动选择：{{name}}',
                                    name: getDesignSystemDisplayTitle(selectedDesignSystem),
                                  })
                                  : t('home.designSystem.autoWithHint', '不指定 - 稍后推荐')}
                              </span>
                              <ChevronDown className="h-4 w-4 shrink-0 text-[var(--app-foreground-subtle)]" aria-hidden="true" />
                            </button>
                          </PopoverTrigger>
                          <PopoverContent
                            align="start"
                            side="top"
                            sideOffset={12}
                            className={cn(
                              'z-[2200] w-[320px] rounded-xl border p-1.5 shadow-xl',
                              'border-[var(--app-border)] bg-[var(--app-glass)] text-foreground backdrop-blur-2xl',
                            )}
                          >
                            <div className="pb-1">
                              <input
                                autoFocus
                                value={designSystemSearchQuery}
                                onChange={(event) => setDesignSystemSearchQuery(event.target.value)}
                                placeholder={t('home.designSystem.searchPlaceholder', 'Search design systems')}
                                className={cn(
                                  'h-8 w-full rounded-lg border px-2.5 text-xs outline-none transition-colors',
                                  'border-[var(--app-border)] bg-[var(--app-control)] text-foreground placeholder:text-muted-foreground focus:border-[var(--app-primary)]',
                                )}
                              />
                            </div>
                            <div className="max-h-[300px] overflow-y-auto">
                              <button
                                type="button"
                                data-state={selectedDesignSystemId ? 'unchecked' : 'checked'}
                                onClick={() => {
                                  selectDesignSystem(null)
                                  setIsDesignSystemSelectOpen(false)
                                }}
                                className={cn(
                                  'relative flex w-full items-start rounded-lg px-2.5 py-2.5 pr-8 text-left focus:bg-blue-500/10 focus:text-current',
                                  selectedDesignSystemId ? '' : isDark ? 'bg-blue-500/15' : 'bg-blue-50',
                                )}
                              >
                                <div className="flex min-w-0 flex-col gap-1">
                                  <span className="text-sm font-semibold">
                                    {t('home.designSystem.autoWithHint', '不指定 - 稍后推荐')}
                                  </span>
                                  <span className={cn('text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
                                    {t('home.designSystem.autoDescription', 'Leave it unset and let AI recommend a design system after the quick brief.')}
                                  </span>
                                </div>
                                {!selectedDesignSystemId ? <Check className="absolute right-2.5 top-3 h-4 w-4" /> : null}
                              </button>
                              {filteredDesignSystems.map((designSystem) => {
                                const selected = selectedDesignSystemId === designSystem.id
                                return (
                                  <div
                                    key={designSystem.id}
                                    className={cn(
                                      'relative mt-1 rounded-lg',
                                      selected ? (isDark ? 'bg-blue-500/15' : 'bg-blue-50') : '',
                                    )}
                                  >
                                    <button
                                      type="button"
                                      data-state={selected ? 'checked' : 'unchecked'}
                                      onClick={() => {
                                        selectDesignSystem(designSystem.id)
                                        setIsDesignSystemSelectOpen(false)
                                      }}
                                      className="flex w-full items-start rounded-lg px-2.5 py-2.5 pr-14 text-left focus:bg-blue-500/10 focus:text-current"
                                    >
                                      <div className="flex min-w-0 items-start gap-3">
                                        <DesignSystemSwatch designSystem={designSystem} isDark={isDark} className="mt-0.5 h-8 w-8 rounded-lg" />
                                        <div className="min-w-0 flex-1 pr-1">
                                          <div className="flex items-center gap-2">
                                            <span className="truncate text-sm font-semibold" title={getDesignSystemDisplayTitle(designSystem)}>
                                              {getDesignSystemDisplayTitle(designSystem)}
                                            </span>
                                          </div>
                                          <div className="mt-1 flex items-start gap-3">
                                            <span
                                              className={cn('min-w-0 flex-1 line-clamp-2 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-500')}
                                              title={getDesignSystemDisplayDescription(designSystem)}
                                            >
                                              {getDesignSystemDisplayDescription(designSystem)}
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                      {selected ? <Check className="absolute right-2.5 top-3 h-4 w-4" /> : null}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(event) => {
                                        event.preventDefault()
                                        event.stopPropagation()
                                        openDesignSystemPreviewFromMenu(designSystem)
                                      }}
                                      aria-label={t('home.designSystem.previewButtonWithName', {
                                        defaultValue: 'Preview {{name}}',
                                        name: getDesignSystemDisplayTitle(designSystem),
                                      })}
                                      className={cn(
                                        'absolute right-2.5 bottom-2.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors',
                                        'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
                                      )}
                                    >
                                      <Eye className="h-3 w-3" />
                                      <span>{t('home.designSystem.showcaseTab', '示例')}</span>
                                    </button>
                                  </div>
                                )
                              })}
                            </div>
                          </PopoverContent>
                        </Popover>
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div
                    className="relative"
                    onMouseEnter={() => setHoveredToolbarIcon('web_search')}
                    onMouseLeave={() => setHoveredToolbarIcon(current => current === 'web_search' ? null : current)}
                  >
                    <button
                      type="button"
                      aria-label={t('canvas.chat.history.web_search', 'Web Search')}
                      aria-pressed={webSearchEnabled}
                      onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                      className={cn(
                        'p-2 rounded-lg transition-colors border',
                        webSearchEnabled
                          ? 'text-blue-500 bg-blue-500/10 border-blue-500/20'
                          : 'border-transparent text-muted-foreground hover:bg-[var(--app-control-hover)]',
                      )}
                    >
                      <Globe className="w-4 h-4" />
                    </button>

                    {hoveredToolbarIcon === 'web_search' ? (
                      <div className="absolute bottom-full left-1/2 z-30 mb-3 w-44 -translate-x-1/2 rounded-2xl border border-[var(--app-border)] bg-[var(--app-glass)] px-3 py-2.5 text-foreground shadow-2xl backdrop-blur-2xl">
                        <div className="text-xs font-semibold">
                          {t('canvas.chat.history.web_search', 'Web Search')}
                        </div>
                        <div className="mt-1 text-[11px] text-zinc-300">
                          {t('canvas.chat.history.web_search_hint', 'Search for real-time information')}
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <HomeChatModelPicker
                    isDark={isDark}
                    thinkingEnabled={homeThinkingEnabled}
                    value={homeModelPreferences}
                    onChange={handleHomePreferencesChange}
                    onImageModelsChange={setHomeAvailableImageModels}
                    onMultimodalModelsChange={setHomeAvailableMultimodalModels}
                  />

                  <HomeChatThinkingPicker
                    isDark={isDark}
                    thinkingEnabled={homeThinkingEnabled}
                    thinkingAvailable={homeThinkingModeAvailable}
                    onThinkingChange={handleHomeThinkingChange}
                  />

                  <HomeChatAttachmentPicker
                    isDark={isDark}
                    disabled={isPrimaryComposerLocked}
                    onFilesSelected={handleLocalFilesSelected}
                    onOpenLibrary={() => setIsAssetLibraryOpen(true)}
                    onOpenReferenceGallery={() => setIsReferenceGalleryPickerOpen(true)}
                  />

                  <div className="w-px h-4 bg-zinc-500/20 mx-1" />

                  {isStreaming || isAgentBusy ? (
                    <button
                      type="button"
                      onClick={stopStreaming}
                      aria-label="Stop agent response"
                      className="p-2 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  ) : isInteractionSubmitting ? (
                    <button
                      type="button"
                      disabled
                      data-testid="home-chat-composer-submit-button"
                      className="p-2 rounded-lg bg-blue-600 text-white shadow-lg shadow-blue-500/20 disabled:opacity-100"
                    >
                      <Loader2 data-testid="home-chat-composer-submit-spinner" className="w-4 h-4 animate-spin" />
                    </button>
                  ) : (
                    <button
                      onClick={handleSend}
                      disabled={!inputValue.trim() || isPrimaryComposerLocked}
                      data-testid="home-chat-composer-submit-button"
                      className={cn('p-2 rounded-lg transition-colors', inputValue.trim() ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'bg-zinc-500/10 text-zinc-500')}
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Mode selector (only on empty state) */}
            {!hasConversationContent && (
              <div className="flex gap-6 mt-8">
                {EMPTY_STATE_VISIBLE_MODES.map(m => {
                  const MIcon = m.icon
                  return (
                    <button key={m.id} onClick={() => handleModeChange(m.id)} className="flex flex-col items-center gap-2 group">
                      <div className={cn(
                        'w-12 h-12 rounded-2xl flex items-center justify-center transition-all',
                        activeMode === m.id
                          ? `${isDark ? m.bg : m.bgLight} ${m.color} scale-110 shadow-md`
                          : 'bg-[var(--app-control)] text-muted-foreground group-hover:bg-[var(--app-control-hover)]'
                      )}>
                        <MIcon className="w-5 h-5" />
                      </div>
                      <span className={cn('text-xs font-medium', activeMode === m.id ? 'text-zinc-900 dark:text-white' : 'text-zinc-500')}>
                        {t(`home.modes.${m.id}`, m.id)}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>
        {isRailPreviewOpen && previewingWorkspaceFile && (
          <HomeChatWorkspacePreviewRail
            testId={
              isHtmlPreviewOpen
                ? 'home-chat-html-preview'
                : isOfficeDocPreviewOpen
                  ? 'home-chat-office-doc-rail'
                  : isOfficeSheetPreviewOpen
                    ? 'home-chat-office-sheet-rail'
                  : isPresentationPreviewOpen
                    ? 'home-chat-office-presentation-rail'
                    : isTextPreviewOpen
                      ? 'home-chat-text-preview'
                      : 'home-chat-markdown-preview'
            }
            title={previewingWorkspaceFile.name}
            metaSummary={runtimePreviewMeta || undefined}
            isDark={isDark}
            onClose={() => void handleCloseWorkspaceFilePreview()}
            onDownload={() => void handleDownloadFile(previewingWorkspaceFile)}
            externalOpenSuites={getExternalOpenSuites(previewingWorkspaceFile)}
            onOpenExternal={
              isExternalOpenSupported(previewingWorkspaceFile)
                ? (suite) => void handleOpenExternalPreviewFile(previewingWorkspaceFile, suite)
                : undefined
            }
            isOpeningExternal={isOpeningExternalPreview}
            isOpenExternalDisabled={isStreaming || isAgentBusy}
            contentClassName={cn(
              'flex-1 min-h-0',
              isHtmlPreviewOpen
                ? 'overflow-hidden'
                : isOfficeSheetPreviewOpen
                  ? 'relative overflow-hidden p-0'
                  : isOfficeDocPreviewOpen || isPresentationPreviewOpen
                  ? 'overflow-hidden p-4'
                  : 'overflow-y-auto px-8 py-6 custom-scrollbar',
            )}
            actionsBeforeDownload={previewingWorkspaceFile.versions?.length ? (
              <HomeChatFileVersionControl
                file={previewingWorkspaceFile}
                selectedVersionId={previewingVersionId}
                isDark={isDark}
                disabled={isStreaming || isAgentBusy}
                onSelectVersion={(versionId) => void handleSelectPreviewVersion(versionId)}
              />
            ) : undefined}
          >
            {isHtmlPreviewOpen ? (
              previewingWorkspaceHtmlUrl ? (
                <iframe
                  title={previewingWorkspaceFile.name}
                  src={previewingWorkspaceHtmlUrl}
                  className="h-full w-full border-0 bg-white"
                  sandbox="allow-same-origin allow-scripts allow-forms allow-modals allow-popups allow-downloads"
                />
              ) : (
                <div className="flex items-center gap-3 px-8 py-6 text-sm text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Loading preview...</span>
                </div>
              )
            ) : isOfficeDocPreviewOpen ? (
              isOfficeSessionLoading ? (
                <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Opening document session...</span>
                </div>
              ) : workspaceFilePreviewError ? (
                <div className="text-sm text-red-500">{workspaceFilePreviewError}</div>
              ) : !previewingOfficeSession?.preview_file_path ? (
                <div className="text-sm text-red-500">Failed to open office preview.</div>
              ) : (
                <Suspense
                  fallback={(
                    <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Opening document session...</span>
                    </div>
                  )}
                >
                  <HomeChatDocHtmlPreview
                    key={previewingOfficeSession.session_id}
                    conversationId={String(conversationId)}
                    previewFilePath={previewingOfficeSession.preview_file_path}
                    title={previewingWorkspaceFile.name}
                  />
                </Suspense>
              )
            ) : isOfficeSheetPreviewOpen ? (
              isOfficeSessionLoading ? (
                <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Opening sheet session...</span>
                </div>
              ) : workspaceFilePreviewError ? (
                <div className="text-sm text-red-500">{workspaceFilePreviewError}</div>
              ) : !previewingOfficeSession ? (
                <div className="text-sm text-red-500">Failed to open office preview.</div>
              ) : previewingOfficeSession.preview_file_path ? (
                <Suspense
                  fallback={(
                    <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Opening sheet session...</span>
                    </div>
                  )}
                >
                  <HomeChatDocHtmlPreview
                    key={previewingOfficeSession.session_id}
                    conversationId={String(conversationId)}
                    previewFilePath={previewingOfficeSession.preview_file_path}
                    title={previewingWorkspaceFile.name}
                  />
                </Suspense>
              ) : (
                <Suspense
                  fallback={(
                    <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Opening sheet session...</span>
                    </div>
                  )}
                >
                  <HomeChatUniverSheetEditor
                    key={previewingOfficeSession.session_id}
                    snapshot={isHomeChatOfficeSheetSnapshot(previewingOfficeSession.snapshot) ? previewingOfficeSession.snapshot : null}
                    isDark={isDark}
                  />
                </Suspense>
              )
            ) : isPresentationPreviewOpen ? (
              isOfficeSessionLoading ? (
                <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Opening presentation session...</span>
                </div>
              ) : workspaceFilePreviewError ? (
                <div className="text-sm text-red-500">{workspaceFilePreviewError}</div>
              ) : previewingOfficeSession?.preview_file_path ? (
                <Suspense
                  fallback={(
                    <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Opening presentation session...</span>
                    </div>
                  )}
                >
                  <HomeChatDocHtmlPreview
                    key={previewingOfficeSession.session_id}
                    conversationId={String(conversationId)}
                    previewFilePath={previewingOfficeSession.preview_file_path}
                    title={previewingWorkspaceFile.name}
                    onPresentationRegenerateSlide={handlePresentationRegenerateSlide}
                    isPresentationRegenerateDisabled={isStreaming || isAgentBusy}
                  />
                </Suspense>
              ) : (
                <Suspense
                  fallback={(
                    <div className="flex h-full items-center gap-3 px-4 text-sm text-zinc-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Opening presentation session...</span>
                    </div>
                  )}
                >
                  <HomeChatPptPreview
                    snapshot={previewingOfficeSession?.snapshot as HomeChatOfficePresentationSnapshot}
                  />
                </Suspense>
              )
            ) : isWorkspaceFilePreviewLoading ? (
              <div className="flex items-center gap-3 text-sm text-zinc-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Loading preview...</span>
              </div>
            ) : workspaceFilePreviewError ? (
              <div className="text-sm text-red-500">{workspaceFilePreviewError}</div>
            ) : isTextPreviewOpen ? (
              <HomeChatPlainTextPreview
                content={previewingWorkspaceFileContent}
                isDark={isDark}
                className="max-w-none"
              />
            ) : (
              <HomeChatMarkdown
                content={previewingWorkspaceFileContent}
                isDark={isDark}
                className="max-w-none"
                conversationId={conversationId}
              />
            )}
          </HomeChatWorkspacePreviewRail>
        )}
      </div>

      <HomeSessionFilesDialog
        open={isFilesModalOpen}
        isDark={isDark}
        activeFileTab={activeFileTab}
        fileTabCounts={fileTabCounts}
        visibleSessionFiles={visibleSessionFiles}
        sessionFiles={sessionFiles}
        conversationId={conversationId}
        onOpenChange={setIsFilesModalOpen}
        onActiveFileTabChange={setActiveFileTab}
        onDownloadFile={handleDownloadFile}
        onPreviewWorkspaceFile={handlePreviewWorkspaceFile}
      />

      {previewingWorkspaceFile && isSessionVideoFile(previewingWorkspaceFile) && !isRailPreviewOpen ? (
        <Dialog open onOpenChange={(open) => !open && handleCloseWorkspaceFilePreview()}>
          <DialogContent className="max-h-[92vh] max-w-[92vw] overflow-hidden border-none bg-transparent p-0 shadow-none [&>button]:rounded-full [&>button]:bg-[var(--app-media-control)] [&>button]:text-white [&>button]:hover:bg-[var(--app-media-control-hover)]">
            <DialogTitle className="sr-only">
              {previewingWorkspaceFile?.name || t('canvas.chat.preview.file', 'File preview')}
            </DialogTitle>
            <DialogDescription className="sr-only">
              {t('canvas.chat.preview.file_description', 'Preview the selected workspace file.')}
            </DialogDescription>
            <div className="relative flex h-full w-full items-center justify-center p-4">
              <video
                data-testid="home-chat-video-preview"
                src={previewingWorkspaceFileUrl}
                className="max-h-[85vh] max-w-full rounded-2xl bg-[var(--app-media-overlay)] shadow-2xl"
                controls
                autoPlay
                playsInline
              />
            </div>
          </DialogContent>
        </Dialog>
      ) : null}

      <ImagePreviewDialog
        open={!!previewingWorkspaceFile && !isRailPreviewOpen && !!(previewingWorkspaceFile && isSessionImageFile(previewingWorkspaceFile) && previewingWorkspaceFileUrl)}
        onOpenChange={(open) => !open && handleCloseWorkspaceFilePreview()}
        src={previewingWorkspaceFile && isSessionImageFile(previewingWorkspaceFile) ? (previewingWorkspaceFileUrl || null) : null}
        alt={previewingWorkspaceFile?.name || t('canvas.chat.preview.file', 'File preview')}
        title={previewingWorkspaceFile?.name || t('canvas.chat.preview.file', 'File preview')}
        imageClassName="rounded-2xl"
        downloadUrl={previewingWorkspaceFile && isSessionImageFile(previewingWorkspaceFile) ? (previewingWorkspaceFileUrl || null) : null}
      />

      <HomeChatAssetLibraryModal
        open={isAssetLibraryOpen}
        onOpenChange={(open) => {
          setIsAssetLibraryOpen(open)
          if (!open) {
            setEcommerceReferenceImageSelect(null)
          }
        }}
        isDark={isDark}
        onSelect={handleLibraryAssetsSelected}
        assetType={ecommerceReferenceImageSelect ? 'image' : undefined}
        lockAssetType={!!ecommerceReferenceImageSelect}
        maxSelection={ecommerceReferenceImageSelect?.maxSelection}
      />
      <ReferenceGalleryPickerModal
        open={isReferenceGalleryPickerOpen}
        onOpenChange={(open) => {
          setIsReferenceGalleryPickerOpen(open)
          if (!open) {
            setEcommerceReferenceImageSelect(null)
          }
        }}
        isDark={isDark}
        selectionMode="multiple"
        maxSelection={ecommerceReferenceImageSelect?.maxSelection}
        onSelect={handleReferenceGalleryImagesSelected}
      />
      <HomeDesignSystemPreviewDialog
        open={isDesignSystemPreviewOpen}
        onOpenChange={setIsDesignSystemPreviewOpen}
        designSystem={selectedDesignSystem}
        isDark={isDark}
      />
      <HomeSkillExamplePreviewDialog
        open={isSkillExamplePreviewOpen}
        onOpenChange={(open) => {
          setIsSkillExamplePreviewOpen(open)
          if (!open) {
            setSkillExamplePreviewSkill(null)
          }
        }}
        skill={skillExamplePreviewSkill}
        skillTitle={skillExamplePreviewSkill ? getLocalizedSkillName(skillExamplePreviewSkill, currentLanguage) : ''}
        examplePrompt={skillExamplePreviewSkill?.example_prompt || ''}
        isDark={isDark}
      />
    </div>
  )
}


