import { FileText, LayoutTemplate, Presentation, TableProperties } from 'lucide-react'
import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useIsDarkMode } from "@/hooks/useTheme"
import { useChatStore } from '@/store/canvasAgentStore'
import { agentApi, type AttachmentData } from '@/api/endpoints/agent'
import { buildCanvasChatSkills, type ChatSkillId } from '.././chatSkills'
import { loadCanvasModelCatalog, enabledProviderModels, registryModels, type CanvasSelectableModel } from '.././canvasModelCatalog'
import { getAppendMentionInsertionPoint, getManualMentionInsertionPoint, moveCursorAfterNode, removeAtomicChipBeforeCaret } from '.././chatComposerDom'
import {
    buildCanvasPendingAttachment,
    CANVAS_CHAT_ATTACHMENT_ACCEPT,
    filterSupportedCanvasChatAttachmentFiles,
    loadCanvasPendingAttachmentPreview,
} from '.././chatAttachmentKinds'
import {
    filterMultimodalModelsForMode,
    getModeSwitchTargetMultimodalModel,
    isThinkingModeAvailableForMultimodalModel,
    pickDefaultMultimodalModel,
    resolveCanvasModelPreferences,
    type SelectableMultimodalModel,
} from '.././chatSidebarModelHelpers'
import { useAuthStore } from '@/store/authStore'
import { useAppConfigStore } from '@/store/appConfigStore'
import { resolveLocalizedProviderName } from '@/config/brand'
import { toast } from 'sonner'
import { ensureBalanceOrNotify, isBalanceRequiredForMultimodalProvider } from '@/utils/balanceGuard'
import { validateUploadFileSize } from '@/utils/uploadLimits'
import { canAccessCanvasPlugins, canAccessHomeAgent } from '@/utils/licenseAccess'
import { handleScrollableWheel } from '.././scrollableWheel'
import { buildCanvasMentionReferences } from '.././canvasMessageReferences'
import {
    buildCanvasAssetAttachmentReference,
    buildCanvasAttachmentReferences,
    mergeCanvasMessageReferences,
} from '.././canvasAttachmentReferences'
import {
    serializeCanvasMarkToken,
    serializeCanvasMentionToken,
} from '.././canvasReferenceTokens'

import { type CanvasItem, type CanvasMark } from '@/api/endpoints/projects'
import { type AssetLibrarySelectedAsset } from '.././AssetLibraryModal'
import type {
    EcommerceReferenceImageRequestOptions,
    EcommerceReferenceImageSource,
} from '@/components/agent/EcommerceInteractionCard'
import { getImageCapabilityFromConfig, type ImageModelRegistryConfig } from '.././imageModelConfig'
import { buildForwardSelectionText } from '.././chatForwardSelection'
import {
    buildHomeForwardTransferReference,
    saveHomeForwardTransfer,
    type HomeForwardTransferMode,
} from '../../HomeHarnessAgent/homeForwardTransfer'
import {
    collectAttachmentBlobUrls,
    revokeAttachmentBlobUrls,
} from '../../agentMedia/agentPendingAttachmentPreview'

export interface ChatSidebarProps {
    isOpen: boolean
    onClose: () => void
    projectId: number
    canvasItems: CanvasItem[]
    appendMentionRequest?: { itemId: string, nonce: number } | null
    deletedAgentMediaKeys: string[]
    canvasItemsLoaded: boolean
    onFocusItem: (itemId: string) => void
    marks: CanvasMark[]
    onRemoveMark: (markId: string) => void
    onUpdateMarkLabel: (markId: string, label: string | null, isCustom: boolean) => void
    onClearMarks: () => void
    onOpenAttachmentLibrary: () => void
    onOpenReferenceGallery?: () => void
    onRequestEcommerceReferenceImages?: (
        source: EcommerceReferenceImageSource,
        onSelect: (urls: string[]) => void,
        options?: EcommerceReferenceImageRequestOptions,
    ) => void
    onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>
    maxEcommerceReferenceImages?: number
    assetLibrarySelection?: { assets: AssetLibrarySelectedAsset[], nonce: number } | null
    pauseThinkingAnimation?: boolean
}

const NUMBER_CIRCLES = ['\u2460', '\u2461', '\u2462', '\u2463', '\u2464', '\u2465', '\u2466', '\u2467', '\u2468', '\u2469']

const MENTION_POPUP_MAX_HEIGHT = 280
const MENTION_POPUP_ITEM_HEIGHT = 56
const MENTION_POPUP_OVERSCAN = 6

export function useChatSidebar({ isOpen, onClose, projectId, canvasItems, appendMentionRequest, deletedAgentMediaKeys, canvasItemsLoaded, onFocusItem, marks, onRemoveMark, onUpdateMarkLabel, onClearMarks, onOpenAttachmentLibrary, onOpenReferenceGallery = () => {}, onRequestEcommerceReferenceImages, onUploadEcommerceReferenceImage, maxEcommerceReferenceImages, assetLibrarySelection, pauseThinkingAnimation = false }: ChatSidebarProps) {
    const { t, i18n } = useTranslation()
    const isDark = useIsDarkMode()
    const appName = useAppConfigStore((s) => s.appName)
    const appNameEn = useAppConfigStore((s) => s.appNameEn)
    const brand = useMemo(() => ({ appName, appNameEn }), [appName, appNameEn])
    const fileInputRef = useRef<HTMLInputElement>(null)
    // We only need to know whether the composer has any text (to toggle the send
    // button). Keeping the *whole* text in React state would re-render the entire
    // sidebar (MessageList, attachment previews, etc.) on every keystroke. Instead
    // store a boolean and bail out when it doesn't change, so typing within
    // non-empty text triggers no re-render. The actual text lives in the
    // contentEditable DOM and is read via getEditorText() when sending.
    const [hasInput, setHasInput] = useState(false)
    const setInputValue = useCallback((text: string) => {
        const next = text.trim().length > 0
        setHasInput((prev) => (prev === next ? prev : next))
    }, [])
    const [isComposerDragActive, setIsComposerDragActive] = useState(false)
    const [hoveredIcon, setHoveredIcon] = useState<string | null>(null)
    const [activeView, setActiveView] = useState<'history' | 'files' | 'models' | 'tools' | null>(null)
    const [uploadedAttachments, setUploadedAttachments] = useState<AttachmentData[]>([])
    // Pending thumbnails are blob URLs. Revoke any that drop out of the list
    // (removed/sent/new-chat) and on unmount to avoid renderer memory buildup.
    const trackedAttachmentUrlsRef = useRef<string[]>([])
    useEffect(() => {
        const currentUrls = collectAttachmentBlobUrls(uploadedAttachments)
        const currentSet = new Set(currentUrls)
        for (const url of trackedAttachmentUrlsRef.current) {
            if (!currentSet.has(url)) {
                URL.revokeObjectURL(url)
            }
        }
        trackedAttachmentUrlsRef.current = currentUrls
    }, [uploadedAttachments])
    useEffect(() => () => {
        for (const url of trackedAttachmentUrlsRef.current) {
            URL.revokeObjectURL(url)
        }
    }, [])
    const [hoveredConvId, setHoveredConvId] = useState<number | string | null>(null)
    const [pendingDeleteConversationId, setPendingDeleteConversationId] = useState<number | string | null>(null)
    const historyRef = useRef<HTMLDivElement>(null)
    const historyButtonRef = useRef<HTMLDivElement>(null)
    const toolsRef = useRef<HTMLDivElement>(null)
    const toolsButtonRef = useRef<HTMLDivElement>(null)
    const [mentionSearch, setMentionSearch] = useState('')
    const [mentionPopupVisible, setMentionPopupVisible] = useState(false)
    const [selectedMentionId, setSelectedMentionId] = useState<string | null>(null)
    const [mentionPopupScrollTop, setMentionPopupScrollTop] = useState(0)
    const [forwardSelectionMode, setForwardSelectionMode] = useState(false)
    const [selectedForwardMessageIds, setSelectedForwardMessageIds] = useState<Set<string>>(new Set())
    const [forwardMode, setForwardMode] = useState<HomeForwardTransferMode | null>(null)
    const [isForwardAssetLibraryOpen, setIsForwardAssetLibraryOpen] = useState(false)
    const textareaRef = useRef<HTMLDivElement>(null)
    const mentionListRef = useRef<HTMLDivElement>(null)
    const processedAppendMentionNonce = useRef<number | null>(null)
    const processedAssetLibrarySelectionNonce = useRef<number | null>(null)
    const savedSelectionRangeRef = useRef<Range | null>(null)
    const autoLoadedConversationRef = useRef<string | null>(null)
    const suppressAutoLoadAfterNewChatRef = useRef(false)
    const autoLoadProjectRef = useRef(projectId)

    useEffect(() => {
        if (!assetLibrarySelection) return
        if (processedAssetLibrarySelectionNonce.current === assetLibrarySelection.nonce) return

        processedAssetLibrarySelectionNonce.current = assetLibrarySelection.nonce
        setUploadedAttachments((prev) => [
            ...prev,
            ...assetLibrarySelection.assets.map((asset) => ({
                type: 'image' as const,
                url: asset.url,
                preview_url: asset.list_preview_url || asset.url,
                name: getAssetLibraryAttachmentName(asset),
                reference: buildCanvasAssetAttachmentReference({
                    url: asset.url,
                    name: getAssetLibraryAttachmentName(asset),
                }),
            })),
        ])
    }, [assetLibrarySelection])

    // Chat store
    const messages = useChatStore(s => s.messages)
    const activePlan = useChatStore(s => s.activePlan)
    const isStreaming = useChatStore(s => s.isStreaming)
    const runStatus = useChatStore((s) => {
        const currentConversationId = s.conversationId
        if (currentConversationId == null) {
            return 'idle'
        }
        return s.conversationSessions[String(currentConversationId)]?.runStatus ?? 'idle'
    })
    const mode = useChatStore(s => s.mode)
    const activeSkillId = useChatStore(s => s.activeSkillId)
    const uiConfig = useChatStore(s => s.uiConfig)
    const streamingBlocks = useChatStore(s => s.streamingBlocks)
    const conversations = useChatStore(s => s.conversations)
    const conversationId = useChatStore(s => s.conversationId)
    const webSearchEnabled = useChatStore(s => s.webSearchEnabled)
    const modelPreferences = useChatStore(s => s.modelPreferences)
    const syncScope = useChatStore(s => s.syncScope)
    const sendMessage = useChatStore(s => s.sendMessage)
    const stopStreaming = useChatStore(s => s.stopStreaming)
    const approvePlan = useChatStore(s => s.approvePlan)
    const rejectPlan = useChatStore(s => s.rejectPlan)
    const setMode = useChatStore(s => s.setMode)
    const activateSkill = useChatStore(s => s.activateSkill)
    const loadConversations = useChatStore(s => s.loadConversations)
    const loadConversation = useChatStore(s => s.loadConversation)
    const createConversation = useChatStore(s => s.createConversation)
    const deleteConversation = useChatStore(s => s.deleteConversation)
    const setWebSearchEnabled = useChatStore(s => s.setWebSearchEnabled)
    const setModelPreferences = useChatStore(s => s.setModelPreferences)
    const loadUiConfig = useChatStore(s => s.loadUiConfig)
    const { user, licenseEdition } = useAuthStore()
    const forwardModeOptions: Array<{ id: HomeForwardTransferMode, label: string, icon: typeof FileText }> = canAccessHomeAgent(licenseEdition)
        ? [
            { id: 'document', label: t('canvas.chat.forward.mode_document', 'Document Generate'), icon: FileText },
            { id: 'ppt', label: t('canvas.chat.forward.mode_ppt', 'PPT Generate'), icon: Presentation },
            { id: 'spreadsheet', label: t('canvas.chat.forward.mode_spreadsheet', 'Spreadsheet Generate'), icon: TableProperties },
            { id: 'web', label: t('canvas.chat.forward.mode_web', 'Web Generate'), icon: LayoutTemplate },
        ]
        : []

    const cleanTitle = (title: string) => {
        if (!title) return ''
        let cleaned = title
            .replace(/@\[([^\]]+)\]\([^)]+\)/g, '$1')
            .replace(/#\[([^\]]*)\]\([^)]+\)/g, '$1')
            .replace(/\s+/g, ' ')
            .trim()
            
        // Remove spaces between CJK characters
        const cjkRegex = /([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])/g;
        cleaned = cleaned.replace(cjkRegex, '$1$2').replace(cjkRegex, '$1$2');
        
        return cleaned
    }

    const formatConversationUpdatedAt = (value: string | null | undefined) => {
        if (!value) return ''
        const date = new Date(value)
        if (Number.isNaN(date.getTime())) return ''
        return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
    }

    const clearForwardSelection = useCallback(() => {
        setForwardSelectionMode(false)
        setSelectedForwardMessageIds(new Set())
        setForwardMode(null)
        setIsForwardAssetLibraryOpen(false)
    }, [])

    const handleEnterForwardSelectionMode = useCallback((messageId: string) => {
        setForwardSelectionMode(true)
        setSelectedForwardMessageIds(new Set([messageId]))
    }, [])

    const handleToggleForwardMessage = useCallback((messageId: string) => {
        setSelectedForwardMessageIds((current) => {
            const next = new Set(current)
            if (next.has(messageId)) {
                next.delete(messageId)
            } else {
                next.add(messageId)
            }
            return next
        })
    }, [])

    const selectedForwardText = buildForwardSelectionText(messages, selectedForwardMessageIds)
    const hasSelectedForwardText = selectedForwardText.trim().length > 0

    const handleOpenForwardAssetLibrary = useCallback((modeId: HomeForwardTransferMode) => {
        if (!hasSelectedForwardText) {
            return
        }
        setForwardMode(modeId)
        setIsForwardAssetLibraryOpen(true)
    }, [hasSelectedForwardText])

    const handleForwardAssetsSelected = useCallback((assets: AssetLibrarySelectedAsset[]) => {
        if (!forwardMode || !hasSelectedForwardText) {
            return
        }

        const transferKey = `home-forward-transfer:${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`
        saveHomeForwardTransfer({
            key: transferKey,
            createdAt: new Date().toISOString(),
            source: 'canvas-agent',
            projectId,
            mode: forwardMode,
            text: selectedForwardText,
            attachments: assets.map((asset) => ({
                id: asset.id,
                url: asset.url,
                type: 'image' as const,
                origin_kind: asset.origin_kind,
                source_asset_id: asset.source_asset_id,
                reference: buildHomeForwardTransferReference(asset),
            })),
        })

        const targetUrl = `/dashboard/home?forwardTransferKey=${encodeURIComponent(transferKey)}`
        const openedWindow = window.open('', '_blank')
        if (!openedWindow) {
            toast.error('无法打开主页智能体窗口，请检查浏览器弹窗权限')
            return
        }

        try {
            openedWindow.opener = null
        } catch {
            // Ignore environments that do not allow mutating opener.
        }

        try {
            openedWindow.location.href = targetUrl
        } catch {
            window.open(targetUrl, '_blank')
        }

        clearForwardSelection()
    }, [clearForwardSelection, forwardMode, hasSelectedForwardText, projectId, selectedForwardText])

    useEffect(() => {
        clearForwardSelection()
    }, [conversationId, clearForwardSelection])

    useEffect(() => {
        if (!forwardSelectionMode) {
            return
        }

        const handleWindowKeyDown = (event: KeyboardEvent) => {
            if (event.key !== 'Escape' || isForwardAssetLibraryOpen) {
                return
            }
            event.preventDefault()
            clearForwardSelection()
        }

        window.addEventListener('keydown', handleWindowKeyDown)
        return () => window.removeEventListener('keydown', handleWindowKeyDown)
    }, [clearForwardSelection, forwardSelectionMode, isForwardAssetLibraryOpen])

    const [availableImageModels, setAvailableImageModels] = useState<{ name: string, value: string, provider: string, providerName: string, isBuiltin: boolean, description?: string, tag?: string, config?: ImageModelRegistryConfig }[]>([])
    const [availableVideoModels, setAvailableVideoModels] = useState<{ name: string, value: string, provider: string, providerName: string, isBuiltin: boolean, description?: string, tag?: string }[]>([])
    const [availableMultimodalModels, setAvailableMultimodalModels] = useState<(SelectableMultimodalModel & { providerName: string, isBuiltin: boolean })[]>([])
    const [modelTab, setModelTab] = useState<'image' | 'video' | 'multimodal'>('image')

    useEffect(() => {
        if (!projectId) {
            return
        }

        if (autoLoadProjectRef.current !== projectId) {
            autoLoadProjectRef.current = projectId
            suppressAutoLoadAfterNewChatRef.current = false
        }

        syncScope(projectId, user?.id ?? null)

        if (isOpen) {
            loadUiConfig()
            loadConversations(projectId)
        }
    }, [isOpen, loadConversations, loadUiConfig, projectId, syncScope, user?.id])

    useEffect(() => {
        if (!isOpen) {
            autoLoadedConversationRef.current = null
            setPendingDeleteConversationId(null)
            return
        }

        if (conversationId != null) {
            autoLoadedConversationRef.current = `${projectId}:${String(conversationId)}`
            suppressAutoLoadAfterNewChatRef.current = false
            return
        }

        if (suppressAutoLoadAfterNewChatRef.current) {
            return
        }

        const firstConversationId = conversations[0]?.id
        if (firstConversationId == null) {
            return
        }

        const autoloadKey = `${projectId}:${String(firstConversationId)}`
        if (autoLoadedConversationRef.current === autoloadKey) {
            return
        }

        autoLoadedConversationRef.current = autoloadKey
        void loadConversation(firstConversationId)
    }, [conversationId, conversations, isOpen, loadConversation, projectId])

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const eventPath = event.composedPath()
            const isGenerationSelectEvent = eventPath.some((target) => (
                target instanceof Element &&
                target.closest('[data-agent-generation-select="true"]')
            ))
            if (isGenerationSelectEvent) return
            if (activeView === 'history' &&
                historyRef.current && !eventPath.includes(historyRef.current) &&
                historyButtonRef.current && !eventPath.includes(historyButtonRef.current)) {
                setActiveView(null)
                setPendingDeleteConversationId(null)
            }
            if (activeView === 'models' &&
                modelsRef.current && !eventPath.includes(modelsRef.current) &&
                modelsButtonRef.current && !eventPath.includes(modelsButtonRef.current)) {
                setActiveView(null)
            }
            if (activeView === 'tools' &&
                toolsRef.current && !eventPath.includes(toolsRef.current) &&
                toolsButtonRef.current && !eventPath.includes(toolsButtonRef.current)) {
                setActiveView(null)
            }
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [activeView])

    useEffect(() => {
        if (activeView === 'tools') {
            void loadUiConfig({ force: true })
        }
    }, [activeView, loadUiConfig])

    const modelsRef = useRef<HTMLDivElement>(null)
    const modelsButtonRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        async function fetchModels() {
            try {
                const { registry, providers } = await loadCanvasModelCatalog();

                const imageModels: CanvasSelectableModel[] = [];
                const videoModels: CanvasSelectableModel[] = [];
                const multimodalModels: CanvasSelectableModel[] = [];

                for (const { provider, models } of providers) {
                    try {
                        const enabledModels = enabledProviderModels({ provider, models }, registry, ['text2image', 'text2video', 'multimodal'])

                        for (const model of enabledModels) {
                            let label = model.model_name;
                            let description = '';
                            let tag = '';
                            const providerRegistry = registry[provider.code];
                            const typeModels = registryModels(providerRegistry, model.model_type);
                            const regModel = typeModels.find(rm => rm.model_name === model.model_name);

                            if (regModel) {
                                label = regModel.label;
                                description = regModel.description || '';
                                if (regModel.config?.typical_duration) {
                                    tag = `${regModel.config.typical_duration}s`;
                                }
                            }

                            const item = {
                                name: label,
                                value: model.model_name,
                                provider: provider.code,
                                providerName: provider.code === 'builtin'
                                    ? resolveLocalizedProviderName(i18n.language, brand, provider.code, provider.name)
                                    : provider.name,
                                isBuiltin: !!provider.is_builtin,
                                description,
                                tag,
                                config: regModel?.config,
                                supportsFastMode: regModel?.config?.supports_fast_mode as boolean | undefined,
                                supportsThinkingMode: regModel?.config?.supports_thinking_mode as boolean | undefined,
                                thinkingVariantOf: regModel?.config?.thinking_variant_of as string | undefined,
                            };

                            if (model.model_type === 'text2image') {
                                imageModels.push(item);
                            } else if (model.model_type === 'text2video') {
                                videoModels.push(item);
                            } else if (model.model_type === 'multimodal') {
                                multimodalModels.push(item);
                            }
                        }
                    } catch (e) {
                        console.error('Failed to fetch models for provider:', provider.code, e);
                    }
                }

                setAvailableImageModels(imageModels);
                setAvailableVideoModels(videoModels);
                setAvailableMultimodalModels(multimodalModels);

            } catch (err) {
                console.error('Failed to fetch models', err);
            }
        }
        if (isOpen) {
            fetchModels();
        }
    }, [brand, i18n.language, isOpen]);

    useEffect(() => {
        if (!isOpen) return
        if (
            availableImageModels.length === 0 &&
            availableVideoModels.length === 0 &&
            availableMultimodalModels.length === 0
        ) {
            return
        }

        const nextPreferences = resolveCanvasModelPreferences(
            modelPreferences,
            {
                imageModels: availableImageModels,
                videoModels: availableVideoModels,
                multimodalModels: availableMultimodalModels,
            },
            mode,
        )
        if (
            nextPreferences.image_model !== modelPreferences.image_model ||
            nextPreferences.image_provider !== modelPreferences.image_provider ||
            nextPreferences.video_model !== modelPreferences.video_model ||
            nextPreferences.video_provider !== modelPreferences.video_provider ||
            nextPreferences.multimodal_model !== modelPreferences.multimodal_model ||
            nextPreferences.multimodal_provider !== modelPreferences.multimodal_provider ||
            nextPreferences.media_generation_settings !== modelPreferences.media_generation_settings
        ) {
            setModelPreferences(nextPreferences)
        }
    }, [
        availableImageModels,
        availableMultimodalModels,
        availableVideoModels,
        isOpen,
        mode,
        modelPreferences,
        setModelPreferences,
    ])

    const filteredMentionItems = useMemo(() => canvasItems.filter(item =>
        (item.type === 'image' || item.type === 'group') &&
        (item.name || item.id).toLowerCase().includes(mentionSearch.toLowerCase())
    ), [canvasItems, mentionSearch])
    const mentionPopupViewportHeight = Math.min(
        MENTION_POPUP_MAX_HEIGHT,
        Math.max(MENTION_POPUP_ITEM_HEIGHT, filteredMentionItems.length * MENTION_POPUP_ITEM_HEIGHT),
    )
    const mentionPopupVisibleStartIndex = Math.max(
        0,
        Math.floor(mentionPopupScrollTop / MENTION_POPUP_ITEM_HEIGHT) - MENTION_POPUP_OVERSCAN,
    )
    const mentionPopupVisibleEndIndex = Math.min(
        filteredMentionItems.length,
        Math.ceil((mentionPopupScrollTop + mentionPopupViewportHeight) / MENTION_POPUP_ITEM_HEIGHT) + MENTION_POPUP_OVERSCAN,
    )
    const visibleMentionItems = filteredMentionItems.slice(mentionPopupVisibleStartIndex, mentionPopupVisibleEndIndex)
    const mentionPopupTopSpacerHeight = mentionPopupVisibleStartIndex * MENTION_POPUP_ITEM_HEIGHT
    const mentionPopupBottomSpacerHeight = Math.max(
        0,
        (filteredMentionItems.length - mentionPopupVisibleEndIndex) * MENTION_POPUP_ITEM_HEIGHT,
    )

    useEffect(() => {
        if (mentionPopupVisible && selectedMentionId && mentionListRef.current) {
            const selectedIndex = filteredMentionItems.findIndex(item => item.id === selectedMentionId)
            if (selectedIndex >= 0) {
                const listEl = mentionListRef.current
                const itemTop = selectedIndex * MENTION_POPUP_ITEM_HEIGHT
                const itemBottom = itemTop + MENTION_POPUP_ITEM_HEIGHT
                const visibleTop = listEl.scrollTop
                const visibleBottom = visibleTop + listEl.clientHeight

                if (itemTop < visibleTop) {
                    listEl.scrollTop = itemTop
                } else if (itemBottom > visibleBottom) {
                    listEl.scrollTop = itemBottom - listEl.clientHeight
                }
            }
        }
    }, [filteredMentionItems, selectedMentionId, mentionPopupVisible])

    // Helper: get child image items for a group
    const getGroupChildren = useCallback((groupId: string) => {
        return canvasItems.filter(ci => ci.groupId === groupId && ci.type === 'image')
    }, [canvasItems])

    const saveEditorSelection = useCallback(() => {
        const editorEl = textareaRef.current
        const selection = window.getSelection()
        if (!editorEl || !selection || selection.rangeCount === 0) return

        const range = selection.getRangeAt(0)
        const startNode = range.startContainer
        const endNode = range.endContainer

        if (!editorEl.contains(startNode) || !editorEl.contains(endNode)) {
            return
        }

        savedSelectionRangeRef.current = range.cloneRange()
    }, [])

    const restoreEditorSelection = useCallback(() => {
        const editorEl = textareaRef.current
        const savedRange = savedSelectionRangeRef.current
        const selection = window.getSelection()
        if (!editorEl || !savedRange || !selection) return false

        if (!editorEl.contains(savedRange.startContainer) || !editorEl.contains(savedRange.endContainer)) {
            savedSelectionRangeRef.current = null
            return false
        }

        selection.removeAllRanges()
        selection.addRange(savedRange.cloneRange())
        return true
    }, [])

    // Only check currentToolCalls (active streaming) for blocking input.
    // Do NOT check messages (persisted history) - otherwise re-entering a conversation
    // with a stuck/still-polling generation task permanently locks the input.
    const hasGeneratingTasks = streamingBlocks.some(block =>
        block.uiKind === 'generation_task' && block.status === 'running'
    )
    const isAgentBusy = runStatus === 'running'
    const isBusy = isStreaming || isAgentBusy || hasGeneratingTasks

    useEffect(() => {
        if (mentionPopupVisible && filteredMentionItems.length > 0) {
            setSelectedMentionId(filteredMentionItems[0].id)
        } else {
            setSelectedMentionId(null)
        }
    }, [mentionPopupVisible, filteredMentionItems])

    useEffect(() => {
        if (!mentionPopupVisible) {
            setMentionPopupScrollTop(0)
        }
    }, [mentionPopupVisible, mentionSearch])

    useEffect(() => {
        const handleSelectionChange = () => {
            saveEditorSelection()
        }

        document.addEventListener('selectionchange', handleSelectionChange)
        return () => document.removeEventListener('selectionchange', handleSelectionChange)
    }, [saveEditorSelection])

    const skills = useMemo(
        () => buildCanvasChatSkills(uiConfig, i18n.language, t),
        [i18n.language, t, uiConfig],
    )

    // Only check currentToolCalls (active streaming) for blocking input.
    // Do NOT check messages (persisted history) - otherwise re-entering a conversation
    // with a stuck/still-polling generation task permanently locks the input.

    const handleSend = async () => {
        const content = getEditorText().trim()
        if (!content || isBusy) return

        const requiresBalance = isBalanceRequiredForMultimodalProvider(modelPreferences.multimodal_provider)
        if (requiresBalance && !ensureBalanceOrNotify(user?.balance_cents, t)) return

        const currentBalanceCents = user?.balance_cents ?? 0
        if (requiresBalance && currentBalanceCents <= 0) {
            toast.error(t('billing.insufficient', '余额不足，无法发起新会话'))
            return
        }


        setInputValue('')
        if (textareaRef.current) textareaRef.current.innerHTML = ''
        let atts = uploadedAttachments.length > 0 ? [...uploadedAttachments] : undefined
        setUploadedAttachments([])
        insertedMarkIds.current.clear()
        onClearMarks() // Clear marks immediately before sending
        if (atts?.some((attachment) => attachment._localFile)) {
            let convId = conversationId
            if (!convId) {
                await createConversation(projectId)
                convId = useChatStore.getState().conversationId
            }

            if (convId) {
                const uploaded: AttachmentData[] = []
                for (const attachment of atts) {
                    if (!attachment._localFile) {
                        uploaded.push(attachment)
                        continue
                    }
                    if (!validateUploadFileSize(attachment._localFile, 'harness_attachment_max_bytes', t)) {
                        continue
                    }

                    try {
                        const response = await agentApi.uploadHarnessAttachment(String(convId), attachment._localFile)
                        uploaded.push({
                            type: response.data.type === 'image' ? 'image' : 'file',
                            url: response.data.url,
                            name: response.data.filename || attachment.name,
                        })
                    } catch (err) {
                        console.error('Upload failed:', err)
                        toast.error(`Failed to upload ${attachment.name || attachment._localFile.name}`)
                    }
                }
                atts = uploaded.length > 0 ? uploaded : undefined
            }
        }
        const references = mergeCanvasMessageReferences(
            buildCanvasAttachmentReferences(atts),
            buildCanvasMentionReferences(content, canvasItems, marks),
        )
        if (references) {
            await sendMessage(content, atts, { references })
        } else {
            await sendMessage(content, atts)
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        saveEditorSelection()
        if (e.nativeEvent.isComposing) return

        if (e.key === 'Backspace' && textareaRef.current) {
            const removedChip = removeAtomicChipBeforeCaret(textareaRef.current)
            if (removedChip) {
                e.preventDefault()

                if (removedChip.markId) {
                    insertedMarkIds.current.delete(removedChip.markId)
                    onRemoveMark(removedChip.markId)
                    setMarkDropdown((current) => current?.markId === removedChip.markId ? null : current)
                }

                setInputValue(getEditorText())
                setMentionPopupVisible(false)
                saveEditorSelection()
                return
            }
        }

        if (mentionPopupVisible) {
            if (e.key === 'ArrowDown') {
                e.preventDefault()
                const currentIndex = filteredMentionItems.findIndex(item => item.id === selectedMentionId)
                const nextIndex = (currentIndex + 1) % filteredMentionItems.length
                setSelectedMentionId(filteredMentionItems[nextIndex].id)
            } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                const currentIndex = filteredMentionItems.findIndex(item => item.id === selectedMentionId)
                const nextIndex = (currentIndex - 1 + filteredMentionItems.length) % filteredMentionItems.length
                setSelectedMentionId(filteredMentionItems[nextIndex].id)
            } else if (e.key === 'Enter') {
                e.preventDefault()
                const selectedItem = filteredMentionItems.find(item => item.id === selectedMentionId)
                if (selectedItem) selectMention(selectedItem)
            } else if (e.key === 'Escape') {
                setMentionPopupVisible(false)
            }
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            if (!isBusy) {
                handleSend()
            }
        }
    }

    const getAttachmentFiles = useCallback((items?: DataTransferItemList | null, files?: FileList | null) => {
        const itemFiles = items
            ? Array.from(items)
                .filter((item) => item.kind === 'file')
                .map((item) => item.getAsFile())
                .filter((file): file is File => Boolean(file))
            : []

        if (itemFiles.length > 0) {
            return itemFiles
        }

        return files ? Array.from(files) : []
    }, [])

    const showUnsupportedUploadToast = useCallback(() => {
        toast.error(t(
            'canvas.chat.upload_unsupported_format',
            'Only images, TXT/MD, DOC/DOCX, XLSX/CSV, and HTML files can be uploaded.',
        ))
    }, [t])

    const appendLocalFiles = useCallback(async (files: File[]) => {
        if (files.length === 0) return

        const { supported, unsupported } = filterSupportedCanvasChatAttachmentFiles(files)
        if (unsupported.length > 0) {
            showUnsupportedUploadToast()
        }
        if (supported.length === 0) {
            return
        }

        const nextAttachments = await Promise.all(supported.map((file) => buildCanvasPendingAttachment(file)))
        setUploadedAttachments((prev) => [...prev, ...nextAttachments])

        for (const [index, attachment] of nextAttachments.entries()) {
            const file = supported[index]
            if (!file || attachment.type !== 'image' || !attachment._clientAttachmentId) {
                continue
            }
            void loadCanvasPendingAttachmentPreview(file).then((preview) => {
                if (!preview.preview_url) {
                    return
                }
                let applied = false
                setUploadedAttachments((current) => current.map((currentAttachment) => {
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

        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }
    }, [showUnsupportedUploadToast])

    // Prevent pasting rich text while allowing clipboard file uploads
    const handlePaste = useCallback(async (e: React.ClipboardEvent) => {
        const attachmentFiles = getAttachmentFiles(e.clipboardData?.items, e.clipboardData?.files)
        if (attachmentFiles.length > 0) {
            e.preventDefault()
            await appendLocalFiles(attachmentFiles)
            return
        }

        e.preventDefault()
        const text = e.clipboardData.getData('text/plain')
        document.execCommand('insertText', false, text)
    }, [appendLocalFiles, getAttachmentFiles])

    const handleComposerDragEnter = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        const attachmentFiles = getAttachmentFiles(e.dataTransfer?.items, e.dataTransfer?.files)
        if (attachmentFiles.length === 0) return
        e.preventDefault()
        setIsComposerDragActive(true)
    }, [getAttachmentFiles])

    const handleComposerDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        const attachmentFiles = getAttachmentFiles(e.dataTransfer?.items, e.dataTransfer?.files)
        if (attachmentFiles.length === 0) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'copy'
        setIsComposerDragActive(true)
    }, [getAttachmentFiles])

    const handleComposerDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
        setIsComposerDragActive(false)
    }, [])

    const handleComposerDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
        const attachmentFiles = getAttachmentFiles(e.dataTransfer?.items, e.dataTransfer?.files)
        setIsComposerDragActive(false)
        if (attachmentFiles.length === 0) return
        e.preventDefault()
        await appendLocalFiles(attachmentFiles)
    }, [appendLocalFiles, getAttachmentFiles])


    // Extract plain text from contentEditable, converting chips back to canonical reference tokens.
    const getEditorText = useCallback(() => {
        if (!textareaRef.current) return ''
        let result = ''
        const walk = (node: Node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                result += node.textContent || ''
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const el = node as HTMLElement
                const mentionId = el.getAttribute('data-mention-id')
                const mentionName = el.getAttribute('data-mention-name')
                const markId = el.getAttribute('data-mark-id')
                if (mentionId && mentionName) {
                    result += serializeCanvasMentionToken(mentionName, mentionId)
                } else if (markId) {
                    const markLabel = el.getAttribute('data-mark-label') || ''
                    const markImageId = el.getAttribute('data-mark-image-id') || ''
                    const markRx = el.getAttribute('data-mark-rx') || '0'
                    const markRy = el.getAttribute('data-mark-ry') || '0'
                    result += serializeCanvasMarkToken(markLabel, markId, markImageId, markRx, markRy)
                } else if (el.tagName === 'BR') {
                    result += '\n'
                } else {
                    el.childNodes.forEach(walk)
                }
            }
        }
        textareaRef.current.childNodes.forEach(walk)
        return result
    }, [])

    // Get text before cursor position (for mention detection), ignoring mention chips
    const getTextBeforeCursor = useCallback(() => {
        const sel = window.getSelection()
        if (!sel || sel.rangeCount === 0 || !textareaRef.current) return ''
        const range = sel.getRangeAt(0)
        // Create a range from start of editor to cursor
        const preRange = document.createRange()
        preRange.setStart(textareaRef.current, 0)
        preRange.setEnd(range.startContainer, range.startOffset)
        // Clone contents and extract text
        const frag = preRange.cloneContents()
        const tempDiv = document.createElement('div')
        tempDiv.appendChild(frag)
        let result = ''
        const walk = (node: Node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                result += node.textContent || ''
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const el = node as HTMLElement
                if (el.getAttribute('data-mention-id')) {
                    result += serializeCanvasMentionToken(
                        el.getAttribute('data-mention-name') || '',
                        el.getAttribute('data-mention-id') || '',
                    )
                } else if (el.tagName === 'BR') {
                    result += '\n'
                } else {
                    el.childNodes.forEach(walk)
                }
            }
        }
        tempDiv.childNodes.forEach(walk)
        return result
    }, [])

    // Track which mark chips have been inserted into the editor
    const insertedMarkIds = useRef<Set<string>>(new Set())

    // Detect mark chip deletion from editor
    const checkMarkChipDeletion = useCallback(() => {
        if (!textareaRef.current) return
        const existingChipIds = new Set<string>()
        textareaRef.current.querySelectorAll('[data-mark-id]').forEach(el => {
            existingChipIds.add(el.getAttribute('data-mark-id')!)
        })
        const toRemove: string[] = []
        insertedMarkIds.current.forEach(id => {
            if (!existingChipIds.has(id)) {
                toRemove.push(id)
            }
        })
        toRemove.forEach(id => {
            insertedMarkIds.current.delete(id)
            onRemoveMark(id)
        })
    }, [onRemoveMark])

    const handleEditorInput = useCallback(() => {
        saveEditorSelection()
        const text = getEditorText()
        setInputValue(text)

        // Check if any mark chips were deleted
        checkMarkChipDeletion()

        // Mention detection
        const textBeforeCursor = getTextBeforeCursor()
        const lastAtIndices = [...textBeforeCursor.matchAll(/@(?!\[)/g)]

        if (lastAtIndices.length > 0) {
            const lastAt = lastAtIndices[lastAtIndices.length - 1]
            const index = lastAt.index!
            const query = textBeforeCursor.substring(index + 1)

            if (!query.includes(' ') && !query.includes('\n')) {
                setMentionSearch(query)
                setMentionPopupVisible(true)
            } else {
                setMentionPopupVisible(false)
            }
        } else {
            setMentionPopupVisible(false)
        }
    }, [checkMarkChipDeletion, getEditorText, getTextBeforeCursor, saveEditorSelection, setInputValue])

    const createMentionChipHtml = useCallback((item: CanvasItem) => {
        const itemName = item.name || t('canvas.chat.item_types.image')

        const thumbUrl = item.url

        const thumbHtml = thumbUrl
            ? `<img src="${thumbUrl}" style="width:18px;height:18px;border-radius:4px;object-fit:cover;flex-shrink:0;" />`
            : `<span style="width:18px;height:18px;border-radius:4px;background:var(--app-control);display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--app-foreground-muted)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline>
                </svg>
              </span>`

        return `<span contenteditable="false" data-mention-id="${item.id}" data-mention-name="${itemName}" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px 2px 4px;border-radius:8px;background:color-mix(in srgb, var(--app-primary) 12%, transparent);border:1px solid color-mix(in srgb, var(--app-primary) 28%, var(--app-border));color:var(--app-primary);font-size:13px;font-weight:500;cursor:pointer;vertical-align:middle;line-height:1.4;margin:0 2px;">${thumbHtml}<span>${itemName}</span></span>`
    }, [t])

    // Insert a single mention chip into the editor, returns the last inserted element
    const insertSingleMentionChip = useCallback((item: CanvasItem, parent: Node, insertBeforeNode: Node | null): HTMLElement => {
        const chipContainer = document.createElement('span')
        chipContainer.innerHTML = createMentionChipHtml(item)
        const chip = chipContainer.firstElementChild as HTMLElement

        chip.addEventListener('click', (e) => {
            e.preventDefault()
            e.stopPropagation()
            onFocusItem(item.id)
        })

        if (insertBeforeNode) {
            parent.insertBefore(chip, insertBeforeNode)
        } else {
            parent.appendChild(chip)
        }

        return chip
    }, [createMentionChipHtml, onFocusItem])

    const moveCursorToEditorEnd = useCallback(() => {
        if (!textareaRef.current) return
        const selection = window.getSelection()
        if (!selection) return

        const range = document.createRange()
        range.selectNodeContents(textareaRef.current)
        range.collapse(false)
        selection.removeAllRanges()
        selection.addRange(range)
    }, [])

    const appendMentionToEnd = useCallback((item: CanvasItem) => {
        if (!textareaRef.current) return

        let itemsToInsert: CanvasItem[]
        if (item.type === 'group') {
            itemsToInsert = getGroupChildren(item.id)
        } else {
            itemsToInsert = [item]
        }

        const editorEl = textareaRef.current
        const uniqueItemsToInsert = itemsToInsert.filter((ci) => !editorEl.querySelector(`[data-mention-id="${ci.id}"]`))
        if (uniqueItemsToInsert.length === 0) {
            textareaRef.current.focus()
            moveCursorToEditorEnd()
            return
        }

        let insertionPoint = getAppendMentionInsertionPoint(editorEl)
        let lastInsertedNode: Node | null = null

        const insertNodeAtEnd = (node: Node) => {
            const { parent, beforeNode } = insertionPoint
            if (beforeNode) {
                parent.insertBefore(node, beforeNode)
            } else {
                parent.appendChild(node)
            }
            lastInsertedNode = node
            insertionPoint = {
                parent: node.parentNode!,
                beforeNode: node.nextSibling,
            }
        }

        const editorText = getEditorText()
        if (editorText.length > 0 && !/[\s\u00A0\u200B]$/.test(editorText)) {
            insertNodeAtEnd(document.createTextNode('\u00A0'))
        }

        for (const ci of uniqueItemsToInsert) {
            const chip = insertSingleMentionChip(ci, insertionPoint.parent, insertionPoint.beforeNode)
            lastInsertedNode = chip
            insertionPoint = {
                parent: chip.parentNode!,
                beforeNode: chip.nextSibling,
            }
            insertNodeAtEnd(document.createTextNode('\u00A0'))
        }

        setMentionPopupVisible(false)
        setInputValue(getEditorText())
        textareaRef.current.focus()
        if (lastInsertedNode) {
            moveCursorAfterNode(lastInsertedNode)
        } else {
            moveCursorToEditorEnd()
        }
    }, [getEditorText, getGroupChildren, insertSingleMentionChip, moveCursorToEditorEnd, setInputValue])

    const selectMention = useCallback((item: CanvasItem) => {
        if (!textareaRef.current) return
        textareaRef.current.focus()
        const selectionRestored = restoreEditorSelection()
        const sel = window.getSelection()
        if ((!sel || sel.rangeCount === 0) && !selectionRestored) return
        if (!sel || sel.rangeCount === 0) return

        // Determine which items to insert chips for
        let itemsToInsert: CanvasItem[]
        if (item.type === 'group') {
            // For groups, insert chips for all child media items
            itemsToInsert = getGroupChildren(item.id)
            if (itemsToInsert.length === 0) {
                setMentionPopupVisible(false)
                return
            }
        } else {
            itemsToInsert = [item]
        }

        // Find the @ text node before cursor and remove the @query text
        const range = sel.getRangeAt(0)
        const textNode = range.startContainer
        if (textNode.nodeType === Node.TEXT_NODE && textNode.textContent) {
            const text = textNode.textContent
            const cursorPos = range.startOffset
            const beforeCursor = text.substring(0, cursorPos)
            const lastAtIdx = beforeCursor.lastIndexOf('@')
            if (lastAtIdx !== -1) {
                const beforeAt = text.substring(0, lastAtIdx)
                const afterCursor = text.substring(cursorPos)
                const parent = textNode.parentNode!
                let insertionPoint = getManualMentionInsertionPoint(textareaRef.current, textNode)
                const movedIntoTrailingBlock = insertionPoint.parent !== parent

                textNode.textContent = beforeAt || (movedIntoTrailingBlock ? '' : '\u200B')
                if (textNode.textContent === '') {
                    parent.removeChild(textNode)
                }

                let lastInserted: Node | null = null

                const insertNodeAtPoint = (node: Node) => {
                    const { parent: insertionParent, beforeNode } = insertionPoint
                    if (beforeNode) {
                        insertionParent.insertBefore(node, beforeNode)
                    } else {
                        insertionParent.appendChild(node)
                    }
                    lastInserted = node
                    insertionPoint = {
                        parent: node.parentNode!,
                        beforeNode: node.nextSibling,
                    }
                }

                // Insert chips for all items
                for (const ci of itemsToInsert) {
                    const chip = insertSingleMentionChip(ci, insertionPoint.parent, insertionPoint.beforeNode)
                    lastInserted = chip
                    insertionPoint = {
                        parent: chip.parentNode!,
                        beforeNode: chip.nextSibling,
                    }
                    insertNodeAtPoint(document.createTextNode('\u00A0'))
                }

                // Append remaining text after cursor
                if (afterCursor) {
                    insertNodeAtPoint(document.createTextNode(afterCursor))
                }

                // Move cursor after the last space
                const newRange = document.createRange()
                const cursorTarget = lastInserted ?? (textNode.isConnected ? textNode : null)
                if (cursorTarget?.nodeType === Node.TEXT_NODE) {
                    newRange.setStart(cursorTarget, (cursorTarget.textContent || '').length)
                } else {
                    newRange.setStartAfter(cursorTarget ?? textareaRef.current)
                }
                newRange.collapse(true)
                sel.removeAllRanges()
                sel.addRange(newRange)
            }
        }

        setMentionPopupVisible(false)
        setInputValue(getEditorText())
        textareaRef.current.focus()
        saveEditorSelection()
    }, [getEditorText, getGroupChildren, insertSingleMentionChip, restoreEditorSelection, saveEditorSelection, setInputValue])

    useEffect(() => {
        if (!appendMentionRequest) return
        if (processedAppendMentionNonce.current === appendMentionRequest.nonce) return

        const targetItem = canvasItems.find(item => item.id === appendMentionRequest.itemId)
        if (!targetItem) return

        processedAppendMentionNonce.current = appendMentionRequest.nonce
        appendMentionToEnd(targetItem)
    }, [appendMentionRequest, canvasItems, appendMentionToEnd])

    // 鈹€鈹€ Mark chip system 鈹€鈹€
    const [markDropdown, setMarkDropdown] = useState<{ markId: string, rect: DOMRect } | null>(null)


    const createMarkChipHtml = useCallback((mark: CanvasMark) => {
        const displayLabel = mark.customLabel || mark.selectedLabel || ''
        const numIcon = NUMBER_CIRCLES[mark.number - 1] || `(${mark.number})`
        const thumbHtml = mark.imageUrl
            ? `<img src="${mark.imageUrl}" style="width:18px;height:18px;border-radius:4px;object-fit:cover;flex-shrink:0;" />`
            : ''

        const showSpinner = mark.isAnalyzing && !displayLabel;
        const spinnerHtml = `<span class="mark-chip-spinner" style="display:${showSpinner ? 'inline-block' : 'none'};width:14px;height:14px;border:2px solid var(--app-primary);border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite;margin:0 4px;vertical-align:middle;"></span>`
        const labelDisplay = `<span class="mark-chip-label" style="display:${!showSpinner ? 'inline' : 'none'}">${displayLabel || '...'}</span>`

        return `<span contenteditable="false" data-mark-id="${mark.id}" data-mark-image-id="${mark.imageItemId}" data-mark-image-url="${mark.imageUrl}" data-mark-label="${displayLabel}" data-mark-number="${mark.number}" data-mark-rx="${mark.relativeX}" data-mark-ry="${mark.relativeY}" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px 2px 4px;border-radius:8px;background:color-mix(in srgb, var(--app-warning) 14%, transparent);border:1px solid color-mix(in srgb, var(--app-warning) 34%, var(--app-border));color:var(--app-warning);font-size:13px;font-weight:500;cursor:pointer;vertical-align:middle;line-height:1.4;margin:0 2px;">${thumbHtml}<span style="font-weight:700;color:var(--app-primary);">${numIcon}</span> ${labelDisplay}${spinnerHtml} <span style="font-size:10px;color:var(--app-foreground-subtle);">&#9662;</span></span>`
    }, [])

    const updateMarkChipInDom = useCallback((markId: string, label: string, isAnalyzing: boolean, number?: number) => {
        if (!textareaRef.current) return
        const chip = textareaRef.current.querySelector(`[data-mark-id="${markId}"]`) as HTMLElement
        if (!chip) return

        const showSpinner = isAnalyzing && !label;

        chip.setAttribute('data-mark-label', label)
        const labelEl = chip.querySelector('.mark-chip-label') as HTMLElement
        if (labelEl) {
            labelEl.textContent = label || '...'
            labelEl.style.display = !showSpinner ? 'inline' : 'none'
        }

        const spinnerEl = chip.querySelector('.mark-chip-spinner') as HTMLElement
        if (spinnerEl) {
            spinnerEl.style.display = showSpinner ? 'inline-block' : 'none'
        }

        if (number !== undefined) {
            chip.setAttribute('data-mark-number', String(number))
            const numEl = chip.querySelector('span[style*="font-weight:700"]')
            if (numEl) numEl.textContent = NUMBER_CIRCLES[number - 1] || `(${number})`
        }
    }, [])

    // Auto-insert mark chips when marks change
    useEffect(() => {
        if (!textareaRef.current) return

        const currentMarkIds = new Set(marks.map(m => m.id))

        // Remove chips for deleted marks
        insertedMarkIds.current.forEach(id => {
            if (!currentMarkIds.has(id)) {
                insertedMarkIds.current.delete(id)
                const chip = textareaRef.current?.querySelector(`[data-mark-id="${id}"]`)
                if (chip) {
                    // remove trailing space
                    if (chip.nextSibling?.nodeType === Node.TEXT_NODE && chip.nextSibling.textContent === '\u00A0') {
                        chip.nextSibling.remove()
                    }
                    chip.remove()
                }
            }
        })

        // Insert new chips and update existing ones
        for (const mark of marks) {
            if (insertedMarkIds.current.has(mark.id)) {
                // Update existing chip number and label
                updateMarkChipInDom(mark.id, mark.customLabel || mark.selectedLabel || '', mark.isAnalyzing, mark.number)
                continue
            }

            insertedMarkIds.current.add(mark.id)

            // Ensure there's a text node before the chip so cursor can be placed before it
            const editorEl = textareaRef.current!
            if (editorEl.childNodes.length === 0 || (editorEl.firstChild && editorEl.firstChild.nodeType === Node.ELEMENT_NODE)) {
                const leadingSpace = document.createTextNode('\u200B')
                editorEl.insertBefore(leadingSpace, editorEl.firstChild)
            }

            const chipContainer = document.createElement('span')
            chipContainer.innerHTML = createMarkChipHtml(mark)
            const chip = chipContainer.firstElementChild as HTMLElement

            chip.addEventListener('click', (e) => {
                e.preventDefault()
                e.stopPropagation()
                const rect = chip.getBoundingClientRect()
                setMarkDropdown({ markId: mark.id, rect })
            })

            editorEl.appendChild(chip)
            const space = document.createTextNode('\u00A0')
            textareaRef.current.appendChild(space)
        }

        setInputValue(getEditorText())
    }, [marks, isDark, createMarkChipHtml, updateMarkChipInDom, getEditorText, setInputValue])

    // Auto-open dropdown for newly added marks
    const prevMarksCount = useRef(marks.length)
    useEffect(() => {
        if (marks.length > prevMarksCount.current) {
            const newMark = marks[marks.length - 1]
            // Wait for DOM to update
            setTimeout(() => {
                if (!textareaRef.current) return
                const chip = textareaRef.current.querySelector(`[data-mark-id="${newMark.id}"]`) as HTMLElement
                if (chip) {
                    const rect = chip.getBoundingClientRect()
                    setMarkDropdown({ markId: newMark.id, rect })
                }
            }, 50)
        }
        prevMarksCount.current = marks.length
    }, [marks])

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || [])
        if (files.length === 0) return
        await appendLocalFiles(files)
    }

    const handleSkillClick = (skillId: ChatSkillId) => {
        activateSkill(activeSkillId === skillId ? null : skillId)
    }

    const handleNewChat = () => {
        suppressAutoLoadAfterNewChatRef.current = true
        useChatStore.getState().newChat()
        setInputValue('')
        setUploadedAttachments((current) => {
            revokeAttachmentBlobUrls(current)
            return []
        })
    }

    const hasMessages = messages.length > 0 || isStreaming
    const currentImageModelName = availableImageModels.find(m => m.value === modelPreferences.image_model && m.provider === modelPreferences.image_provider)?.name || modelPreferences.image_model || t('canvas.chat.auto')
    const currentVideoModelName = availableVideoModels.find(m => m.value === modelPreferences.video_model && m.provider === modelPreferences.video_provider)?.name || modelPreferences.video_model || t('canvas.chat.auto')
    const currentMultimodalModelName = availableMultimodalModels.find(m => m.value === modelPreferences.multimodal_model && m.provider === modelPreferences.multimodal_provider)?.name || modelPreferences.multimodal_model || t('canvas.chat.auto')
    const currentImageModelCapability = useMemo(() => {
        const currentImageModel = availableImageModels.find(m => (
            m.value === modelPreferences.image_model && m.provider === modelPreferences.image_provider
        ))
        return getImageCapabilityFromConfig(currentImageModel?.config, modelPreferences.image_model)
    }, [availableImageModels, modelPreferences.image_model, modelPreferences.image_provider])
    const effectiveMaxEcommerceReferenceImages = maxEcommerceReferenceImages ?? currentImageModelCapability.maxReferenceImages
    const thinkingModeAvailable = useMemo(() => (
        isThinkingModeAvailableForMultimodalModel(availableMultimodalModels, {
            value: modelPreferences.multimodal_model,
            provider: modelPreferences.multimodal_provider,
        })
    ), [availableMultimodalModels, modelPreferences.multimodal_model, modelPreferences.multimodal_provider])



    return {
isOpen, isDark, t, cleanTitle, conversations, conversationId, activeView, setActiveView, activeSkillId, skills, handleSkillClick, activateSkill, toolsButtonRef, toolsRef, handleNewChat, loadConversations, projectId, setPendingDeleteConversationId, historyButtonRef, historyRef, hoveredConvId, setHoveredConvId, pendingDeleteConversationId, loadConversation, deleteConversation, formatConversationUpdatedAt, hasMessages, messages, streamingBlocks, isStreaming, runStatus, onFocusItem, canvasItems, deletedAgentMediaKeys, canvasItemsLoaded, forwardSelectionMode, selectedForwardMessageIds, handleEnterForwardSelectionMode, handleToggleForwardMessage, activePlan, approvePlan, rejectPlan, uploadedAttachments, setUploadedAttachments, clearForwardSelection, forwardModeOptions, hasSelectedForwardText, handleOpenForwardAssetLibrary, hasInput, isBusy, textareaRef, handleEditorInput, handleKeyDown, saveEditorSelection, handlePaste, handleComposerDragEnter, handleComposerDragOver, handleComposerDragLeave, handleComposerDrop, isComposerDragActive, mentionPopupVisible, filteredMentionItems, mentionListRef, handleScrollableWheel, setMentionPopupScrollTop, mentionPopupTopSpacerHeight, visibleMentionItems, getGroupChildren, selectedMentionId, setSelectedMentionId, restoreEditorSelection, selectMention, mentionPopupBottomSpacerHeight, markDropdown, marks, onUpdateMarkLabel, updateMarkChipInDom, setMarkDropdown, fileInputRef, handleFileUpload, onOpenAttachmentLibrary, onOpenReferenceGallery, onRequestEcommerceReferenceImages, onUploadEcommerceReferenceImage, maxEcommerceReferenceImages: effectiveMaxEcommerceReferenceImages, mode, setMode, availableMultimodalModels, pickDefaultMultimodalModel, getModeSwitchTargetMultimodalModel, setModelPreferences, modelPreferences, modelsButtonRef, hoveredIcon, setHoveredIcon, currentImageModelName, currentVideoModelName, currentMultimodalModelName, modelsRef, modelTab, setModelTab, availableImageModels, availableVideoModels, filterMultimodalModelsForMode, webSearchEnabled, setWebSearchEnabled, stopStreaming, handleSend, isForwardAssetLibraryOpen, setIsForwardAssetLibraryOpen, setForwardMode, handleForwardAssetsSelected, onClose, thinkingModeAvailable, attachmentAccept: CANVAS_CHAT_ATTACHMENT_ACCEPT,
                showPluginsTab: canAccessCanvasPlugins(licenseEdition),
                pauseThinkingAnimation,
    }
}

function getAssetLibraryAttachmentName(asset: AssetLibrarySelectedAsset) {
    const path = asset.url.split('?')[0] || asset.url
    const parts = path.split('/')
    return parts[parts.length - 1] || '素材库图片'
}



export type ChatSidebarShellProps = ReturnType<typeof useChatSidebar>
