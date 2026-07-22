// @ts-nocheck
import {
    Plus, History, X, Paperclip, Bot, Lightbulb, Zap, ArrowUp, Film, Square, Trash2, Globe, Box, Check, Loader2, Image as ImageIcon, Layers, MessageSquare, FileText, Presentation, TableProperties, LayoutTemplate, SlidersHorizontal,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'
import { MediaGenerationSettingsPanel } from '@/components/agent/MediaGenerationSettingsPanel'
import { getMediaGenerationSettingsSummary } from '@/components/agent/mediaGenerationSettingsSummary'

import { MessageList } from '../MessageList'
import { PlanCard } from '../PlanCard'
import { SkillLibraryButton } from '../SkillLibraryButton'
import { GeneratorImageSourcePicker } from './GeneratorImageSourcePicker'
import { AssetLibraryModal } from '../AssetLibraryModal'
import { ChatAttachmentStrip } from './ChatAttachmentStrip'

const MENTION_POPUP_MAX_HEIGHT = 280
const MENTION_POPUP_ITEM_HEIGHT = 56

export function ChatSidebarShell(props: any) {
    const {
        isOpen, isDark, t, cleanTitle, conversations, conversationId, activeView, setActiveView, activeSkillId, skills, handleSkillClick, activateSkill, toolsButtonRef, toolsRef, handleNewChat, loadConversations, projectId, setPendingDeleteConversationId, historyButtonRef, historyRef, hoveredConvId, setHoveredConvId, pendingDeleteConversationId, loadConversation, deleteConversation, formatConversationUpdatedAt, hasMessages, messages, streamingBlocks, isStreaming, runStatus, onFocusItem, canvasItems, deletedAgentMediaKeys, canvasItemsLoaded, forwardSelectionMode, selectedForwardMessageIds, handleEnterForwardSelectionMode, handleToggleForwardMessage, activePlan, approvePlan, rejectPlan, uploadedAttachments, setUploadedAttachments, clearForwardSelection, forwardModeOptions, hasSelectedForwardText, handleOpenForwardAssetLibrary, hasInput, isBusy, textareaRef, handleEditorInput, handleKeyDown, saveEditorSelection, handlePaste, handleComposerDragEnter, handleComposerDragOver, handleComposerDragLeave, handleComposerDrop, isComposerDragActive, mentionPopupVisible, filteredMentionItems, mentionListRef, handleScrollableWheel, setMentionPopupScrollTop, mentionPopupTopSpacerHeight, visibleMentionItems, getGroupChildren, selectedMentionId, setSelectedMentionId, restoreEditorSelection, selectMention, mentionPopupBottomSpacerHeight, markDropdown, marks, onUpdateMarkLabel, updateMarkChipInDom, setMarkDropdown, fileInputRef, handleFileUpload, onOpenAttachmentLibrary, onOpenReferenceGallery, onRequestEcommerceReferenceImages, onUploadEcommerceReferenceImage, maxEcommerceReferenceImages, mode, setMode, availableMultimodalModels, pickDefaultMultimodalModel, getModeSwitchTargetMultimodalModel, setModelPreferences, modelPreferences, modelsButtonRef, hoveredIcon, setHoveredIcon, currentImageModelName, currentVideoModelName, currentMultimodalModelName, modelsRef, modelTab, setModelTab, availableImageModels, availableVideoModels, filterMultimodalModelsForMode, webSearchEnabled, setWebSearchEnabled, stopStreaming, handleSend, isForwardAssetLibraryOpen, setIsForwardAssetLibraryOpen, setForwardMode, handleForwardAssetsSelected, onClose, thinkingModeAvailable, showPluginsTab, attachmentAccept, pauseThinkingAnimation,
    } = props

    const thinkingDisabled = mode !== 'plan' && !thinkingModeAvailable
    const thinkingTooltipDescription = thinkingDisabled
        ? t('canvas.chat.modes.thinking_unavailable', 'Current model does not support thinking mode')
        : t('canvas.chat.modes.thinking_desc')
    const showStopButton = isStreaming || runStatus === 'running'
    const stopDeletePopoverEvent = (event: any) => {
        event.stopPropagation()
    }
    const [pendingAttachmentPreview, setPendingAttachmentPreview] = useState(null)
    const [expandedGenerationSettingsKey, setExpandedGenerationSettingsKey] = useState(null)
    const attachmentPreviewLabel = t('canvas.chat.attachment_preview', 'Attachment preview')

    useEffect(() => {
        setExpandedGenerationSettingsKey(null)
    }, [modelTab])

    useEffect(() => {
        if (activeView !== 'models') {
            setExpandedGenerationSettingsKey(null)
        }
    }, [activeView])

    useEffect(() => () => {
        if (pendingAttachmentPreview?.ownedUrl) {
            URL.revokeObjectURL(pendingAttachmentPreview.ownedUrl)
        }
    }, [pendingAttachmentPreview?.ownedUrl])

    const handlePendingAttachmentPreview = (url: string) => {
        const attachment = uploadedAttachments.find((candidate: any) => (
            candidate.url === url || candidate.preview_url === url || candidate._previewObjectUrl === url
        ))
        const localFile = attachment?._localFile
        if (localFile) {
            const objectUrl = URL.createObjectURL(localFile)
            setPendingAttachmentPreview((current: any) => {
                if (current?.ownedUrl) {
                    URL.revokeObjectURL(current.ownedUrl)
                }
                return {
                    src: objectUrl,
                    alt: attachment.name || localFile.name || attachmentPreviewLabel,
                    ownedUrl: objectUrl,
                }
            })
            return
        }
        if (url) {
            setPendingAttachmentPreview((current: any) => {
                if (current?.ownedUrl) {
                    URL.revokeObjectURL(current.ownedUrl)
                }
                return {
                    src: url,
                    alt: attachment?.name || attachmentPreviewLabel,
                }
            })
        }
    }

    const IconButton = ({ icon: Icon, id, label, onClick }: { icon: any, id: string, label: string, onClick?: () => void }) => (
        <TooltipProvider delayDuration={0}>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div
                        style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                        onClick={onClick}
                    >
                        <Icon 
                            size={18} 
                            color={hoveredIcon === id ? "var(--app-primary)" : "var(--app-foreground-muted)"} 
                            onMouseEnter={() => setHoveredIcon(id)}
                            onMouseLeave={() => setHoveredIcon(null)}
                            style={{ cursor: 'pointer', transition: 'color 0.2s' }} 
                        />
                    </div>
                </TooltipTrigger>
                <TooltipContent side="bottom" sideOffset={12}>
                    {label}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    )

    if (!isOpen) return null

    return (
        <div
            className="nowheel"
            data-testid="chat-sidebar"
            style={{
                position: 'absolute',
                top: 16,
                right: 16,
                bottom: 16,
                width: 500,
                backgroundColor: 'var(--app-glass)',
                borderRadius: 24,
                boxShadow: 'var(--app-shadow-panel)',
                border: '1px solid var(--app-border)',
                backdropFilter: 'var(--app-blur)',
                WebkitBackdropFilter: 'var(--app-blur)',
                display: 'flex',
                flexDirection: 'column',
                zIndex: 2147483646,
                overflow: 'hidden',
                animation: 'slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                userSelect: 'text',
                WebkitUserSelect: 'text',
                contain: 'layout paint',
                transform: 'translateZ(0)',
                willChange: pauseThinkingAnimation ? 'transform' : 'auto',
            }}
        >
            {/* Header */}
            <div style={{ 
                padding: '20px 24px', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between',
                borderBottom: '1px solid var(--app-border)',
                backgroundColor: 'var(--app-surface-muted)',
                borderRadius: '24px 24px 0 0',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                    <div style={{ 
                        width: 32, height: 32, borderRadius: 10, 
                        backgroundColor: 'var(--app-primary)', display: 'flex', 
                        alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0
                    }}>
                        <MessageSquare size={16} color="var(--app-primary-foreground)" />
                    </div>
                    
                    <TooltipProvider delayDuration={200}>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <div 
                                    style={{ 
                                        fontSize: 17, 
                                        fontWeight: 700, 
                                        color: 'var(--app-foreground)', 
                                        letterSpacing: '-0.01em',
                                        whiteSpace: 'nowrap',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        flex: 1,
                                        minWidth: 0,
                                        cursor: 'default'
                                    }}>
                                    {cleanTitle(conversations.find(c => c.id === conversationId)?.title || t('canvas.chat.new_chat'))}
                                </div>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" className="max-w-[400px] break-words">
                                {cleanTitle(conversations.find(c => c.id === conversationId)?.title || t('canvas.chat.new_chat'))}
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <SkillLibraryButton
                        isDark={isDark}
                        open={activeView === 'tools'}
                        showPluginsTab={showPluginsTab}
                        activeSkillId={activeSkillId ?? null}
                        skills={skills}
                        buttonLabel={t('canvas.chat.header.tools')}
                        panelTitle={t('canvas.chat.tools_title')}
                        clearLabel={t('canvas.chat.header.clear_skill')}
                        skillsTabLabel={t('canvas.chat.tabs.skills')}
                        pluginsTabLabel={t('canvas.chat.tabs.plugins')}
                        plugins={[
                            {
                                id: 'prompt_extractor',
                                title: t('canvas.chat.plugins.prompt_extractor.title'),
                                description: t('canvas.chat.plugins.prompt_extractor.description'),
                                actionLabel: t('canvas.chat.plugins.prompt_extractor.action'),
                            },
                            {
                                id: 'photoshop_uxp',
                                title: t('canvas.chat.plugins.photoshop_uxp.title'),
                                description: t('canvas.chat.plugins.photoshop_uxp.description'),
                                actionLabel: t('canvas.chat.plugins.photoshop_uxp.action'),
                            },
                        ]}
                        onToggle={() => setActiveView(activeView === 'tools' ? null : 'tools')}
                        onSelect={(skillId) => {
                            handleSkillClick(skillId)
                            setActiveView(null)
                        }}
                        onClear={() => {
                            activateSkill(null)
                            setActiveView(null)
                        }}
                        buttonRef={toolsButtonRef}
                        panelRef={toolsRef}
                    />

                    <IconButton icon={Plus} id="new" label={t('canvas.chat.header.new_chat')} onClick={handleNewChat} />

                    <div style={{ position: 'relative' }} ref={historyButtonRef}>
                        <IconButton
                            icon={History}
                            id="history"
                            label={t('canvas.chat.header.history')}
                            onClick={() => {
                                if (activeView !== 'history') {
                                    loadConversations(projectId)
                                    setPendingDeleteConversationId(null)
                                }
                                const nextView = activeView === 'history' ? null : 'history'
                                setActiveView(nextView)
                                if (nextView !== 'history') {
                                    setPendingDeleteConversationId(null)
                                }
                            }}
                        />
                        {activeView === 'history' && (
                            <div
                                ref={historyRef}
                                style={{
                                    position: 'absolute',
                                    top: '100%',
                                    right: 0,
                                    transform: 'translateY(12px)',
                                    width: 320,
                                    backgroundColor: 'var(--app-glass)',
                                    borderRadius: 16,
                                    boxShadow: 'var(--app-shadow-panel)',
                                    border: '1px solid var(--app-border)',
                                    backdropFilter: 'var(--app-blur)',
                                    WebkitBackdropFilter: 'var(--app-blur)',
                                    padding: '16px',
                                    zIndex: 1200,
                                    animation: 'fadeIn 0.2s ease-out'
                                }}>
                                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: 'var(--app-foreground)' }}>
                                    {t('canvas.chat.history.title')}
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 300, overflowY: 'auto', overflowX: 'visible', paddingRight: 8 }}>
                                    {conversations.map((conv, index) => {
                                        const shouldOpenDeletePopoverUpward = index >= conversations.length - 2

                                        return (
                                        <div
                                            key={conv.id}
                                            data-testid={`conversation-history-row-${conv.id}`}
                                            onMouseEnter={() => setHoveredConvId(conv.id)}
                                            onMouseLeave={() => setHoveredConvId(null)}
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'space-between',
                                                padding: '8px 12px',
                                                borderRadius: 100,
                                                backgroundColor: conv.id === conversationId ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'transparent',
                                                cursor: 'pointer',
                                                transition: 'background-color 0.2s',
                                                position: 'relative',
                                                overflow: 'visible',
                                            }}
                                            onClick={() => { loadConversation(conv.id); setActiveView(null) }}
                                        >
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                                                <TooltipProvider delayDuration={200}>
                                                    <Tooltip>
                                                        <TooltipTrigger asChild>
                                                            <div style={{
                                                                fontSize: 13,
                                                                color: conv.id === conversationId ? 'var(--app-primary)' : 'var(--app-foreground-muted)',
                                                                whiteSpace: 'nowrap',
                                                                overflow: 'hidden',
                                                                textOverflow: 'ellipsis',
                                                                flex: 1,
                                                            }}>
                                                                {cleanTitle(conv.title)}
                                                            </div>
                                                        </TooltipTrigger>
                                                        <TooltipContent side="right" className="max-w-[300px] break-words">
                                                            {cleanTitle(conv.title)}
                                                        </TooltipContent>
                                                    </Tooltip>
                                                </TooltipProvider>
                                                <span
                                                    data-testid={`conversation-updated-at-${conv.id}`}
                                                    style={{
                                                        fontSize: 12,
                                                        color: 'var(--app-foreground-subtle)',
                                                        flexShrink: 0,
                                                    }}
                                                >
                                                    {formatConversationUpdatedAt(conv.updated_at)}
                                                </span>
                                            </div>
                                            {hoveredConvId === conv.id || pendingDeleteConversationId === conv.id ? (
                                                <Popover
                                                    open={pendingDeleteConversationId === conv.id}
                                                    onOpenChange={(open) => {
                                                        setPendingDeleteConversationId(open ? conv.id : null)
                                                    }}
                                                >
                                                    <PopoverTrigger asChild>
                                                        <button
                                                            type="button"
                                                            data-testid={`conversation-delete-trigger-${conv.id}`}
                                                            aria-label={t('common.confirm', '删除')}
                                                            style={{
                                                                marginLeft: 8,
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                justifyContent: 'center',
                                                                border: 'none',
                                                                background: 'transparent',
                                                                padding: 0,
                                                                cursor: 'pointer',
                                                            }}
                                                            onClick={(e) => {
                                                                e.stopPropagation()
                                                            }}
                                                        >
                                                            <Trash2
                                                                size={14}
                                                                color="var(--app-danger)"
                                                                style={{ opacity: 0.7 }}
                                                            />
                                                        </button>
                                                    </PopoverTrigger>
                                                    <PopoverContent
                                                        data-testid={`conversation-delete-popover-${conv.id}`}
                                                        side={shouldOpenDeletePopoverUpward ? 'top' : 'bottom'}
                                                        align="end"
                                                        sideOffset={10}
                                                        onPointerDown={stopDeletePopoverEvent}
                                                        onMouseDown={stopDeletePopoverEvent}
                                                        onClick={stopDeletePopoverEvent}
                                                        className="z-[2147483647] w-auto border-0 p-0 shadow-none"
                                                        style={{
                                                            backgroundColor: 'var(--app-surface)',
                                                            border: '1px solid var(--app-border)',
                                                            borderRadius: 12,
                                                            boxShadow: 'var(--app-shadow-panel)',
                                                            padding: '18px 18px 16px',
                                                            minWidth: 228,
                                                            minHeight: 96,
                                                            overflow: 'visible',
                                                        }}
                                                    >
                                                        <div
                                                            style={{
                                                                fontSize: 14,
                                                                fontWeight: 500,
                                                                color: 'var(--app-foreground)',
                                                                marginBottom: 14,
                                                                whiteSpace: 'nowrap',
                                                                lineHeight: 1.5,
                                                                minHeight: 22,
                                                            }}
                                                        >
                                                            {t('canvas.chat.history.delete_confirm', '删除这个会话？')}
                                                        </div>
                                                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 14 }}>
                                                            <button
                                                                type="button"
                                                                data-testid={`conversation-delete-cancel-${conv.id}`}
                                                                style={{
                                                                    border: 'none',
                                                                    background: 'transparent',
                                                                    color: 'var(--app-foreground-subtle)',
                                                                    fontSize: 14,
                                                                    cursor: 'pointer',
                                                                    padding: '2px 0',
                                                                    lineHeight: 1.4,
                                                                    minHeight: 24,
                                                                }}
                                                                onClick={() => setPendingDeleteConversationId(null)}
                                                            >
                                                                {t('common.cancel', '取消')}
                                                            </button>
                                                            <button
                                                                type="button"
                                                                data-testid={`conversation-delete-confirm-button-${conv.id}`}
                                                                style={{
                                                                    border: 'none',
                                                                    background: 'transparent',
                                                                    color: 'var(--app-danger)',
                                                                    fontSize: 14,
                                                                    fontWeight: 600,
                                                                    cursor: 'pointer',
                                                                    padding: '2px 0',
                                                                    lineHeight: 1.4,
                                                                    minHeight: 24,
                                                                }}
                                                                onClick={() => {
                                                                    void deleteConversation(conv.id)
                                                                    setPendingDeleteConversationId(null)
                                                                }}
                                                            >
                                                                {t('common.confirm', '删除')}
                                                            </button>
                                                        </div>
                                                    </PopoverContent>
                                                </Popover>
                                            ) : null}
                                        </div>
                                    )})}
                                    {conversations.length === 0 && (
                                        <div style={{ padding: 12, textAlign: 'center', color: 'var(--app-foreground-subtle)', fontSize: 13 }}>
                                            {t('canvas.chat.history.empty')}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    <IconButton icon={X} id="close" label={t('canvas.chat.header.close')} onClick={onClose} />
                </div>
            </div>

            {/* Main Content Area */}
            {!hasMessages ? (
                /* Welcome / Skills view */
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 40px' }}>
                    <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 32, color: 'var(--app-foreground)', letterSpacing: '-0.01em' }}>
                        {t('canvas.chat.try_skills')}
                    </div>
                    <div style={{ display: 'flex', gap: '12px 12px', width: '100%', justifyContent: 'center', flexWrap: 'wrap' }}>
                        {skills.map((skill) => {
                            const Icon = skill.icon
                            return (
                                <button
                                    key={skill.id}
                                    type="button"
                                    onClick={() => handleSkillClick(skill.id)}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 8,
                                        padding: '10px 18px',
                                        borderRadius: 14,
                                        border: '1px solid var(--app-border)',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                                        backgroundColor: 'transparent',
                                        fontSize: 14,
                                        fontWeight: 600,
                                        color: 'var(--app-foreground-muted)',
                                        boxShadow: 'var(--app-shadow-control)',
                                        whiteSpace: 'nowrap',
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.backgroundColor = 'var(--app-control-hover)'
                                        e.currentTarget.style.borderColor = skill.color + '44'
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.backgroundColor = 'transparent'
                                        e.currentTarget.style.borderColor = 'var(--app-border)'
                                    }}
                                >
                                    <div style={{ color: skill.color, display: 'flex', alignItems: 'center' }}><Icon size={16} /></div>
                                    {skill.name}
                                </button>
                            )
                        })}
                    </div>
                </div>
            ) : (
                /* Messages view */
                <>
                    <MessageList
                        messages={messages}
                        streamingBlocks={streamingBlocks}
                        isStreaming={isStreaming}
                        conversationId={conversationId}
                        runStatus={runStatus}
                        onFocusItem={onFocusItem}
                        canvasItems={canvasItems}
                        deletedAgentMediaKeys={deletedAgentMediaKeys}
                        canReplayCompletedMedia={canvasItemsLoaded}
                        forwardSelectionMode={forwardSelectionMode}
                        selectedForwardMessageIds={selectedForwardMessageIds}
                        onEnterForwardSelectionMode={handleEnterForwardSelectionMode}
                        onToggleForwardMessage={handleToggleForwardMessage}
                        pauseThinkingAnimation={pauseThinkingAnimation}
                        onRequestEcommerceReferenceImages={onRequestEcommerceReferenceImages}
                        onUploadEcommerceReferenceImage={onUploadEcommerceReferenceImage}
                        maxEcommerceReferenceImages={maxEcommerceReferenceImages}
                    />

                    {/* Plan card */}
                    {activePlan && (
                        <div style={{ padding: '0 20px' }}>
                            <PlanCard
                                plan={activePlan}
                                onApprove={approvePlan}
                                onReject={rejectPlan}
                            />
                        </div>
                    )}

                </>
            )}

            {/* Uploaded file previews */}
            {uploadedAttachments.length > 0 && (
                <div style={{ padding: '0 20px 8px' }}>
                    <ChatAttachmentStrip
                        attachments={uploadedAttachments}
                        isDark={isDark}
                        conversationId={conversationId}
                        onRemove={(index) => setUploadedAttachments((prev) => prev.filter((_, i) => i !== index))}
                        onPreview={handlePendingAttachmentPreview}
                    />
                </div>
            )}

            {/* Footer / Input Area */}
            <div style={{ 
                padding: '24px 20px 32px',
                borderTop: '1px solid var(--app-border)',
                backgroundColor: 'var(--app-surface-muted)',
                position: 'relative',
                boxShadow: 'var(--app-shadow-panel)',
                borderRadius: '0 0 24px 24px',
            }}>
                {forwardSelectionMode && (
                    <button
                        type="button"
                        aria-label={t('canvas.chat.forward.cancel_selection', 'Cancel forward selection')}
                        onClick={clearForwardSelection}
                        style={{
                            position: 'absolute',
                            top: 10,
                            right: 12,
                            width: 28,
                            height: 28,
                            borderRadius: 999,
                            border: 'none',
                            backgroundColor: 'transparent',
                            color: 'var(--app-foreground-muted)',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            zIndex: 1,
                        }}
                    >
                        <X size={16} />
                    </button>
                )}
                {forwardSelectionMode && (
                    <div style={{
                        display: 'block',
                        marginBottom: 16,
                        paddingRight: 32,
                        overflowX: 'hidden',
                    }}>
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
                            gap: 8,
                            width: '100%',
                        }}>
                            {forwardModeOptions.map((option) => {
                                const Icon = option.icon
                                return (
                                    <button
                                        key={option.id}
                                        type="button"
                                        disabled={!hasSelectedForwardText}
                                        onClick={() => handleOpenForwardAssetLibrary(option.id)}
                                        style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            gap: 8,
                                            height: 36,
                                            width: '100%',
                                            justifyContent: 'center',
                                            padding: '0 10px',
                                            borderRadius: 999,
                                            border: '1px solid var(--app-border)',
                                            backgroundColor: 'var(--app-control)',
                                            color: 'var(--app-foreground)',
                                            fontSize: 12,
                                            fontWeight: 600,
                                            cursor: hasSelectedForwardText ? 'pointer' : 'not-allowed',
                                            opacity: hasSelectedForwardText ? 1 : 0.45,
                                            minWidth: 0,
                                        }}
                                    >
                                        <Icon size={14} style={{ flexShrink: 0 }} />
                                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{option.label}</span>
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                )}
                {/* Active Skill Chip - above input box */}
                {activeSkillId && (() => {
                    const activeSkill = skills.find(s => s.id === activeSkillId)
                    if (!activeSkill) return null
                    const Icon = activeSkill.icon
                    return (
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 12,
                            flexWrap: 'wrap',
                            marginBottom: 16,
                        }}>
                        <div style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 6,
                            padding: '6px 14px 6px 12px',
                            borderRadius: 100,
                            backgroundColor: 'var(--app-primary)',
                            boxShadow: 'var(--app-shadow-control)',
                            cursor: 'default',
                            transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                            animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                        }}>
                            <div style={{ color: 'var(--app-primary-foreground)', display: 'flex', alignItems: 'center' }}>
                                <Icon size={14} strokeWidth={2.5} />
                            </div>
                            <span style={{
                                fontSize: 13,
                                fontWeight: 700,
                                color: 'var(--app-primary-foreground)',
                                letterSpacing: '0.01em',
                            }}>{activeSkill.name}</span>
                            <div 
                                onClick={() => activateSkill(null)}
                                style={{ 
                                    display: 'flex', 
                                    alignItems: 'center', 
                                    justifyContent: 'center',
                                    marginLeft: 6,
                                    padding: 2,
                                    borderRadius: '50%',
                                    backgroundColor: 'var(--app-media-control)',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s'
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--app-media-control-hover)'}
                                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--app-media-control)'}
                            >
                                <X size={12} color="var(--app-primary-foreground)" strokeWidth={3} />
                            </div>
                        </div>
                        </div>
                    )
                })()}
                <div style={{
                    borderRadius: 24,
                    border: '1px solid var(--app-border)',
                    padding: '16px 20px',
                    display: 'flex',
                    flexDirection: 'column',
                    backgroundColor: 'var(--app-surface)',
                    boxShadow: 'var(--app-shadow-panel)',
                    transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                }}>
                <div style={{ position: 'relative' }}>
                        <div
                            ref={textareaRef}
                            contentEditable={!isBusy}
                            suppressContentEditableWarning
                            onInput={handleEditorInput}
                            onKeyDown={handleKeyDown}
                            onFocus={saveEditorSelection}
                            onMouseUp={saveEditorSelection}
                            onKeyUp={saveEditorSelection}
                            onPaste={handlePaste}
                            onDragEnter={handleComposerDragEnter}
                            onDragOver={handleComposerDragOver}
                            onDragLeave={handleComposerDragLeave}
                            onDrop={handleComposerDrop}
                            data-placeholder={isBusy ? t('canvas.chat.generating_placeholder') : t('canvas.chat.placeholder')}
                            style={{
                                width: '100%',
                                minHeight: 80,
                                maxHeight: 160,
                                overflowY: 'auto',
                                border: 'none',
                                outline: 'none',
                                backgroundColor: isComposerDragActive ? 'color-mix(in srgb, var(--app-primary) 10%, transparent)' : 'transparent',
                                fontSize: 14,
                                lineHeight: 1.6,
                                color: 'var(--app-foreground)',
                                marginBottom: 12,
                                opacity: isBusy ? 0.6 : 1,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                boxShadow: isComposerDragActive ? '0 0 0 2px var(--app-focus-ring)' : 'none',
                                transition: 'box-shadow 0.15s ease, background-color 0.15s ease',
                            }}
                        />

                        {mentionPopupVisible && filteredMentionItems.length > 0 && (
                            <div 
                                data-testid="mention-popup"
                                style={{
                                position: 'absolute',
                                bottom: '100%',
                                left: 0,
                                marginBottom: 8,
                                width: 320,
                                backgroundColor: 'var(--app-glass)',
                                backdropFilter: 'var(--app-blur)',
                                WebkitBackdropFilter: 'var(--app-blur)',
                                borderRadius: 20,
                                boxShadow: 'var(--app-shadow-panel)',
                                border: '1px solid var(--app-border)',
                                padding: '12px',
                                zIndex: 1500,
                                overflowX: 'hidden',
                                animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)'
                            }}>
                                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--app-foreground-subtle)', padding: '0 8px 8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {t('canvas.chat.this_project')}
                                </div>
                                <div
                                    ref={mentionListRef}
                                    data-testid="mention-popup-scroll"
                                    className="nowheel"
                                    onWheel={handleScrollableWheel}
                                    onScroll={(e) => setMentionPopupScrollTop(e.currentTarget.scrollTop)}
                                    style={{ maxHeight: MENTION_POPUP_MAX_HEIGHT, overflowY: 'auto', overflowX: 'hidden' }}
                                >
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    {mentionPopupTopSpacerHeight > 0 && <div style={{ height: mentionPopupTopSpacerHeight, flexShrink: 0 }} />}
                                    {visibleMentionItems.map((item) => {
                                        const isGroup = item.type === 'group'
                                        const groupChildCount = isGroup ? getGroupChildren(item.id).length : 0
                                        return (
                                        <div
                                            key={item.id}
                                            data-mention-item-id={item.id}
                                            className="mention-item"
                                            onMouseDown={(e) => {
                                                e.preventDefault()
                                                restoreEditorSelection()
                                            }}
                                            onClick={() => selectMention(item)}
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: 12,
                                                padding: '10px 12px',
                                                minHeight: MENTION_POPUP_ITEM_HEIGHT,
                                                boxSizing: 'border-box',
                                                borderRadius: 12,
                                                cursor: 'pointer',
                                                transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                                                backgroundColor: selectedMentionId === item.id
                                                    ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)'
                                                    : 'transparent',
                                                transform: selectedMentionId === item.id ? 'translateX(4px)' : 'none',
                                            }}
                                            onMouseEnter={() => setSelectedMentionId(item.id)}
                                        >
                                            <div style={{
                                                width: 32, height: 32, borderRadius: 100, overflow: 'hidden',
                                                backgroundColor: isGroup ? 'color-mix(in srgb, var(--app-primary) 12%, var(--app-control))' : 'var(--app-control)', flexShrink: 0,
                                                border: isGroup ? '1px solid color-mix(in srgb, var(--app-primary) 28%, var(--app-border))' : '1px solid var(--app-border)',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center'
                                            }}>
                                                {isGroup ? (
                                                    <Layers size={14} color="var(--app-primary)" />
                                                ) : item.url ? (
                                                    <img src={item.url} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                                ) : (
                                                    <ImageIcon size={14} color="var(--app-foreground-subtle)" />
                                                )}
                                            </div>
                                            <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                                                <div style={{
                                                    fontSize: 14,
                                                    fontWeight: 500,
                                                    color: selectedMentionId === item.id ? 'var(--app-primary)' : 'var(--app-foreground)',
                                                    whiteSpace: 'nowrap',
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis'
                                                }}>
                                                    {isGroup
                                                        ? (item.name || t('canvas.chat.item_types.group'))
                                                        : (item.name || t('canvas.chat.item_types.image'))}
                                                </div>
                                                <div style={{ fontSize: 11, color: 'var(--app-foreground-subtle)', marginTop: 1 }}>
                                                    {isGroup
                                                        ? t('canvas.chat.item_types.group_children_count', { count: groupChildCount })
                                                        : t('canvas.chat.item_types.image')}
                                                </div>
                                            </div>
                                            {selectedMentionId === item.id && (
                                                <ArrowUp size={14} color="var(--app-primary)" style={{ transform: 'rotate(45deg)', opacity: 0.8 }} />
                                            )}
                                        </div>
                                        )
                                    })}
                                    {mentionPopupBottomSpacerHeight > 0 && <div style={{ height: mentionPopupBottomSpacerHeight, flexShrink: 0 }} />}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Mark label dropdown */}
                        {markDropdown && (() => {
                            const mark = marks.find(m => m.id === markDropdown.markId)
                            if (!mark) return null
                            return (
                                <>
                                    <div style={{ position: 'fixed', inset: 0, zIndex: 1999 }} onClick={() => setMarkDropdown(null)} />
                                    <div style={{
                                        position: 'fixed',
                                        top: markDropdown.rect.top - 8,
                                        left: markDropdown.rect.left,
                                        transform: 'translateY(-100%)',
                                        backgroundColor: 'var(--app-glass)',
                                        backdropFilter: 'var(--app-blur)',
                                        borderRadius: 16,
                                        boxShadow: 'var(--app-shadow-panel)',
                                        border: '1px solid var(--app-border)',
                                        padding: 8,
                                        zIndex: 2000,
                                        minWidth: 200,
                                    }}>
                                        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--app-foreground-subtle)', padding: '4px 12px 8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                            {t('canvas.chat.mark_dropdown_title')}
                                        </div>
                                        {mark.aiLabels.map(label => {
                                            const isSelected = mark.selectedLabel === label && !mark.customLabel
                                            return (
                                                <div
                                                    key={label}
                                                    onClick={() => {
                                                        onUpdateMarkLabel(mark.id, label, false)
                                                        updateMarkChipInDom(mark.id, label, false)
                                                        setMarkDropdown(null)
                                                    }}
                                                    style={{
                                                        padding: '8px 12px', borderRadius: 10, cursor: 'pointer',
                                                        display: 'flex', alignItems: 'center', gap: 10,
                                                        backgroundColor: isSelected ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'transparent',
                                                        transition: 'background 0.15s',
                                                    }}
                                                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = isSelected ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'var(--app-control-hover)'}
                                                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = isSelected ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'transparent'}
                                                >
                                                    <div style={{ width: 32, height: 32, borderRadius: 100, overflow: 'hidden', flexShrink: 0, border: '1px solid var(--app-border)' }}>
                                                        <img src={mark.imageUrl} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                                    </div>
                                                    <span style={{ flex: 1, fontSize: 14, fontWeight: 500, color: 'var(--app-foreground)' }}>{label}</span>
                                                    {isSelected && <Check size={16} color="var(--app-primary)" />}
                                                </div>
                                            )
                                        })}
                                        <div style={{ borderTop: '1px solid var(--app-border)', margin: '4px 0', padding: '4px 0 0' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px' }}>
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--app-foreground-subtle)" strokeWidth="2"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" /><circle cx="12" cy="10" r="3" /></svg>
                                                <input
                                                    placeholder={t('canvas.chat.custom_label')}
                                                    defaultValue={mark.customLabel || ''}
                                                    autoFocus={mark.aiLabels.length === 0}
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter') {
                                                            const val = (e.target as HTMLInputElement).value.trim()
                                                            if (val) {
                                                                onUpdateMarkLabel(mark.id, val, true)
                                                                updateMarkChipInDom(mark.id, val, false)
                                                                setMarkDropdown(null)
                                                            }
                                                        }
                                                    }}
                                                    style={{
                                                        flex: 1, padding: '6px 0', border: 'none', outline: 'none',
                                                        backgroundColor: 'transparent', fontSize: 13,
                                                        color: 'var(--app-foreground)',
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </>
                            )
                        })()}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <input
                                type="file"
                                ref={fileInputRef}
                                style={{ display: 'none' }}
                                accept={attachmentAccept}
                                multiple
                                onChange={handleFileUpload}
                            />
                            <GeneratorImageSourcePicker
                                isDark={isDark}
                                label={t('canvas.chat.upload_file')}
                                localLabel={t('home.chat.local_upload', 'Local Upload')}
                                libraryLabel={t('home.chat.asset_library', 'Asset Library')}
                                referenceLibraryLabel={t('home.chat.reference_gallery', 'Reference Gallery')}
                                triggerVariant="icon"
                                icon={Paperclip}
                                iconSize={18}
                                inactiveIconColor="var(--app-foreground-muted)"
                                triggerStyle={{ width: 18, height: 18 }}
                                onPickLocal={() => fileInputRef.current?.click()}
                                onPickFromLibrary={onOpenAttachmentLibrary}
                                onPickFromReferenceLibrary={onOpenReferenceGallery}
                            />
                            <div style={{
                                padding: '4px 10px',
                                borderRadius: 20,
                                border: '1px solid var(--app-primary)',
                                color: 'var(--app-primary)',
                                fontSize: 12,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                cursor: 'pointer'
                            }}>
                                <Bot size={14} /> {t('canvas.chat.agent')}
                            </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            {/* Mode Toggle */}
                            <div style={{
                                backgroundColor: 'var(--app-control-track)',
                                borderRadius: 100,
                                padding: 2,
                                display: 'flex',
                                alignItems: 'center',
                                position: 'relative'
                            }}>
                                <div style={{
                                    position: 'absolute',
                                    left: mode === 'plan' ? 2 : 'calc(50% + 1px)',
                                    width: 'calc(50% - 3px)',
                                    height: 'calc(100% - 4px)',
                                    backgroundColor: 'var(--app-control-selected)',
                                    borderRadius: 100,
                                    boxShadow: 'var(--app-shadow-selected)',
                                    transition: 'left 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
                                }} />
                                <div style={{ position: 'relative', zIndex: 1, display: 'flex', alignItems: 'center' }}>
                                    <div
                                        onMouseEnter={() => setHoveredIcon('thinking')}
                                        onMouseLeave={() => setHoveredIcon(null)}
                                        onClick={() => {
                                            if (thinkingDisabled) return
                                            setMode('plan')
                                            const m = getModeSwitchTargetMultimodalModel(
                                                availableMultimodalModels,
                                                mode,
                                                'plan',
                                                { value: modelPreferences.multimodal_model, provider: modelPreferences.multimodal_provider },
                                            ) ?? pickDefaultMultimodalModel(availableMultimodalModels, 'plan')
                                            if (m) setModelPreferences({ multimodal_model: m.value, multimodal_provider: m.provider })
                                        }}
                                        style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: thinkingDisabled ? 'not-allowed' : 'pointer', opacity: thinkingDisabled ? 0.5 : 1 }}
                                    >
                                        <Lightbulb size={18} color={mode === 'plan' ? 'var(--app-foreground)' : 'var(--app-foreground-muted)'} />
                                        {hoveredIcon === 'thinking' && (
                                            <div style={{
                                                position: 'absolute', bottom: '100%', left: 0, marginBottom: 8,
                                                backgroundColor: 'var(--app-glass)', color: 'var(--app-foreground)', padding: '8px 12px', borderRadius: 12, width: 160, zIndex: 2000, border: '1px solid var(--app-border)', boxShadow: 'var(--app-shadow-panel)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)'
                                            }}>
                                                <div style={{ fontWeight: 600, fontSize: 13 }}>{t('canvas.chat.modes.thinking')}</div>
                                                <div style={{ fontSize: 11, color: 'var(--app-foreground-muted)', marginTop: 2 }}>{thinkingTooltipDescription}</div>
                                            </div>
                                        )}
                                    </div>
                                    <div
                                        onMouseEnter={() => setHoveredIcon('quick')}
                                        onMouseLeave={() => setHoveredIcon(null)}
                                        onClick={() => {
                                            setMode('fast')
                                            const m = getModeSwitchTargetMultimodalModel(
                                                availableMultimodalModels,
                                                mode,
                                                'fast',
                                                { value: modelPreferences.multimodal_model, provider: modelPreferences.multimodal_provider },
                                            ) ?? pickDefaultMultimodalModel(availableMultimodalModels, 'fast')
                                            if (m) setModelPreferences({ multimodal_model: m.value, multimodal_provider: m.provider })
                                        }}
                                        style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                                    >
                                        <Zap size={18} color={mode === 'fast' ? 'var(--app-foreground)' : 'var(--app-foreground-muted)'} />
                                        {hoveredIcon === 'quick' && (
                                            <div style={{
                                                position: 'absolute', bottom: '100%', right: 0, marginBottom: 8,
                                                backgroundColor: 'var(--app-glass)', color: 'var(--app-foreground)', padding: '8px 12px', borderRadius: 12, width: 160, zIndex: 2000, border: '1px solid var(--app-border)', boxShadow: 'var(--app-shadow-panel)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)'
                                            }}>
                                                <div style={{ fontWeight: 600, fontSize: 13 }}>{t('canvas.chat.modes.quick')}</div>
                                                <div style={{ fontSize: 11, color: 'var(--app-foreground-muted)', marginTop: 2 }}>{t('canvas.chat.modes.quick_desc')}</div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Web Search Toggle */}
                            {/* Model Preference Toggle */}
                            <div style={{ position: 'relative' }}>
                                <div
                                    ref={modelsButtonRef}
                                    onClick={() => setActiveView(activeView === 'models' ? null : 'models')}
                                    onMouseEnter={() => setHoveredIcon('models')}
                                    onMouseLeave={() => setHoveredIcon(null)}
                                    style={{
                                        width: 36,
                                        height: 36,
                                        borderRadius: 100,
                                        backgroundColor: 'color-mix(in srgb, var(--app-primary) 10%, transparent)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s',
                                        border: '1px solid color-mix(in srgb, var(--app-primary) 22%, var(--app-border))'
                                    }}>
                                    <Box size={18} color="var(--app-primary)" />
                                    {hoveredIcon === 'models' && (
                                        <div style={{
                                            position: 'absolute', bottom: '100%', right: 0, marginBottom: 12,
                                            backgroundColor: 'var(--app-glass)', color: 'var(--app-foreground)', padding: '12px 16px', borderRadius: 16, width: 220, zIndex: 2000,
                                            boxShadow: 'var(--app-shadow-panel)',
                                            border: '1px solid var(--app-border)',
                                            backdropFilter: 'var(--app-blur)',
                                            WebkitBackdropFilter: 'var(--app-blur)',
                                            display: 'flex', flexDirection: 'column', gap: 12,
                                            animation: 'slideUp 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
                                        }}>
                                            <div>
                                                <div style={{ fontSize: 11, color: 'var(--app-foreground-subtle)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' }}>{t('canvas.chat.item_types.image')}</div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 500 }}>
                                                    <div style={{ width: 18, height: 18, borderRadius: 100, backgroundColor: 'var(--app-control)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                        <ImageIcon size={10} color="var(--app-foreground)" />
                                                    </div>
                                                    {currentImageModelName}
                                                </div>
                                            </div>
                                            <div>
                                                <div style={{ fontSize: 11, color: 'var(--app-foreground-subtle)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' }}>{t('canvas.chat.item_types.video')}</div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 500 }}>
                                                    <div style={{ width: 18, height: 18, borderRadius: 100, backgroundColor: 'var(--app-control)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                        <Film size={10} color="var(--app-foreground)" />
                                                    </div>
                                                    {currentVideoModelName}
                                                </div>
                                            </div>
                                            <div>
                                                <div style={{ fontSize: 11, color: 'var(--app-foreground-subtle)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' }}>{t('providers.multimodal')}</div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 500 }}>
                                                    <div style={{ width: 18, height: 18, borderRadius: 100, backgroundColor: 'var(--app-control)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                        <Bot size={10} color="var(--app-foreground)" />
                                                    </div>
                                                    {currentMultimodalModelName}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {activeView === 'models' && (
                                    <div
                                        ref={modelsRef}
                                        style={{
                                            position: 'absolute',
                                            bottom: '100%',
                                            right: 0,
                                            marginBottom: 12,
                                            width: 320,
                                            backgroundColor: 'var(--app-glass)',
                                            borderRadius: 16,
                                            boxShadow: 'var(--app-shadow-panel)',
                                            border: '1px solid var(--app-border)',
                                            backdropFilter: 'var(--app-blur)',
                                            WebkitBackdropFilter: 'var(--app-blur)',
                                            padding: '16px 0',
                                            zIndex: 2000,
                                            animation: 'fadeIn 0.2s ease-out'
                                        }}
                                    >
                                        <div style={{ padding: '0 20px 12px', display: 'flex', alignItems: 'center' }}>
                                            <div style={{ fontWeight: 600, fontSize: 16, color: 'var(--app-foreground)' }}>{t('canvas.chat.model_preferences')}</div>
                                        </div>

                                        <div style={{ padding: '0 12px 12px', display: 'flex' }}>
                                            <div style={{ display: 'flex', backgroundColor: 'var(--app-control-track)', borderRadius: 10, padding: 3, width: '100%' }}>
                                                <div
                                                    onClick={() => setModelTab('image')}
                                                    style={{
                                                        flex: 1, textAlign: 'center', padding: '6px 0', borderRadius: 100, cursor: 'pointer', fontSize: 13,
                                                        backgroundColor: modelTab === 'image' ? 'var(--app-control-selected)' : 'transparent',
                                                        color: modelTab === 'image' ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)',
                                                        boxShadow: modelTab === 'image' ? 'var(--app-shadow-selected)' : 'none',
                                                        transition: 'all 0.2s',
                                                        fontWeight: modelTab === 'image' ? 500 : 400
                                                    }}>
                                                    {t('agent.modelGenerationSettings.imageTab')}
                                                </div>
                                                <div
                                                    onClick={() => setModelTab('video')}
                                                    style={{
                                                        flex: 1, textAlign: 'center', padding: '6px 0', borderRadius: 100, cursor: 'pointer', fontSize: 13,
                                                        backgroundColor: modelTab === 'video' ? 'var(--app-control-selected)' : 'transparent',
                                                        color: modelTab === 'video' ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)',
                                                        boxShadow: modelTab === 'video' ? 'var(--app-shadow-selected)' : 'none',
                                                        transition: 'all 0.2s',
                                                        fontWeight: modelTab === 'video' ? 500 : 400
                                                    }}>
                                                    {t('agent.modelGenerationSettings.videoTab')}
                                                </div>
                                                <div
                                                    onClick={() => setModelTab('multimodal')}
                                                    style={{
                                                        flex: 1, textAlign: 'center', padding: '6px 0', borderRadius: 100, cursor: 'pointer', fontSize: 13,
                                                        backgroundColor: modelTab === 'multimodal' ? 'var(--app-control-selected)' : 'transparent',
                                                        color: modelTab === 'multimodal' ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)',
                                                        boxShadow: modelTab === 'multimodal' ? 'var(--app-shadow-selected)' : 'none',
                                                        transition: 'all 0.2s',
                                                        fontWeight: modelTab === 'multimodal' ? 500 : 400
                                                    }}>
                                                    {t('providers.multimodal')}
                                                </div>
                                            </div>
                                        </div>

                                        <div style={{ maxHeight: 300, overflowY: 'auto', padding: '0 12px' }}>
                                            {(() => {
                                                let filteredModels = [];
                                                if (modelTab === 'image') filteredModels = availableImageModels;
                                                else if (modelTab === 'video') filteredModels = availableVideoModels;
                                                else {
                                                    filteredModels = filterMultimodalModelsForMode(availableMultimodalModels, mode);
                                                }

                                                return filteredModels.map((m) => {
                                                    const isSelected = modelTab === 'image'
                                                        ? (modelPreferences.image_model === m.value && modelPreferences.image_provider === m.provider)
                                                        : modelTab === 'video'
                                                            ? (modelPreferences.video_model === m.value && modelPreferences.video_provider === m.provider)
                                                            : (modelPreferences.multimodal_model === m.value && modelPreferences.multimodal_provider === m.provider);
                                                    const generationType = modelTab === 'image' || modelTab === 'video' ? modelTab : null;
                                                    const settingsKey = `${modelTab}-${m.provider}-${m.value}`;
                                                    const settingsExpanded = expandedGenerationSettingsKey === settingsKey;
                                                    const ModelIcon = modelTab === 'image' ? ImageIcon : modelTab === 'video' ? Film : Bot;
                                                    const settingsSummary = generationType
                                                        ? getMediaGenerationSettingsSummary({
                                                            type: generationType,
                                                            model: m,
                                                            preferences: modelPreferences,
                                                            t,
                                                        }).join(' · ')
                                                        : '';
                                                    const selectModel = () => {
                                                        if (modelTab === 'image') {
                                                            setModelPreferences({ image_model: m.value, image_provider: m.provider });
                                                        } else if (modelTab === 'video') {
                                                            setModelPreferences({ video_model: m.value, video_provider: m.provider });
                                                        } else {
                                                            setModelPreferences({ multimodal_model: m.value, multimodal_provider: m.provider });
                                                        }
                                                    };

                                                    return (
                                                        <div
                                                            key={`${modelTab}-${m.provider}-${m.value}`}
                                                            style={{ marginBottom: 6 }}
                                                        >
                                                            <div
                                                                onClick={selectModel}
                                                                style={{
                                                                    padding: '12px',
                                                                    borderRadius: 12,
                                                                    cursor: 'pointer',
                                                                    display: 'flex',
                                                                    alignItems: 'flex-start',
                                                                    gap: 12,
                                                                    backgroundColor: isSelected ? 'color-mix(in srgb, var(--app-primary) 10%, transparent)' : 'transparent',
                                                                    border: isSelected ? '1px solid color-mix(in srgb, var(--app-primary) 22%, var(--app-border))' : '1px solid transparent',
                                                                    transition: 'all 0.2s'
                                                                }}
                                                            >
                                                                <div style={{
                                                                    width: 32, height: 32, borderRadius: 100, backgroundColor: 'var(--app-control)',
                                                                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: isSelected ? 'var(--app-primary)' : 'var(--app-foreground-muted)',
                                                                    flexShrink: 0
                                                                }}>
                                                                    <ModelIcon size={18} />
                                                                </div>
                                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                                                                        <div style={{ fontWeight: 500, fontSize: 13, color: 'var(--app-foreground)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.name}</div>
                                                                        {isSelected && <Check size={14} color="var(--app-primary)" />}
                                                                    </div>
                                                                    <div style={{ fontSize: 11, color: 'var(--app-foreground-subtle)', marginTop: 2 }}>{m.description || m.providerName}</div>
                                                                    {(m.tag || generationType) && (
                                                                        <div style={{ minHeight: 28, marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                                                                            {generationType ? (
                                                                                <div
                                                                                    title={settingsSummary}
                                                                                    style={{
                                                                                        flex: 1,
                                                                                        minWidth: 0,
                                                                                        overflow: 'hidden',
                                                                                        textOverflow: 'ellipsis',
                                                                                        whiteSpace: 'nowrap',
                                                                                        fontSize: 10,
                                                                                        lineHeight: '16px',
                                                                                        color: 'var(--app-foreground-subtle)',
                                                                                    }}
                                                                                >
                                                                                    {settingsSummary}
                                                                                </div>
                                                                            ) : m.tag ? (
                                                                                <div style={{
                                                                                    display: 'inline-block', padding: '1px 4px', borderRadius: 4, backgroundColor: 'var(--app-control)',
                                                                                    fontSize: 10, color: 'var(--app-foreground-subtle)'
                                                                                }}>
                                                                                    {m.tag}
                                                                                </div>
                                                                            ) : <span />}
                                                                            {generationType && (
                                                                                <button
                                                                                    type="button"
                                                                                    aria-label={t('agent.modelGenerationSettings.title')}
                                                                                    aria-expanded={settingsExpanded}
                                                                                    title={t('agent.modelGenerationSettings.title')}
                                                                                    onKeyDown={(event) => {
                                                                                        event.stopPropagation();
                                                                                    }}
                                                                                    onClick={(event) => {
                                                                                        event.stopPropagation();
                                                                                        setExpandedGenerationSettingsKey((current) => current === settingsKey ? null : settingsKey);
                                                                                    }}
                                                                                    style={{
                                                                                        marginLeft: 'auto',
                                                                                        width: 28,
                                                                                        height: 28,
                                                                                        borderRadius: 8,
                                                                                        border: settingsExpanded ? '1px solid color-mix(in srgb, var(--app-primary) 30%, var(--app-border))' : '1px solid var(--app-border)',
                                                                                        backgroundColor: settingsExpanded ? 'color-mix(in srgb, var(--app-primary) 10%, transparent)' : 'var(--app-control)',
                                                                                        color: settingsExpanded ? 'var(--app-primary)' : 'var(--app-foreground-muted)',
                                                                                        display: 'flex',
                                                                                        alignItems: 'center',
                                                                                        justifyContent: 'center',
                                                                                        cursor: 'pointer',
                                                                                        transition: 'all 0.2s'
                                                                                    }}
                                                                                >
                                                                                    <SlidersHorizontal size={14} />
                                                                                </button>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            {generationType && settingsExpanded && (
                                                                <div style={{ paddingTop: 6 }}>
                                                                    <MediaGenerationSettingsPanel
                                                                        type={generationType}
                                                                        model={m}
                                                                        preferences={modelPreferences}
                                                                        onChange={setModelPreferences}
                                                                        compact
                                                                        showHeader={false}
                                                                    />
                                                                </div>
                                                            )}
                                                        </div>
                                                    )
                                                })
                                            })()}
                                            {modelTab === 'multimodal' && mode === 'plan' && filterMultimodalModelsForMode(availableMultimodalModels, mode).length === 0 && (
                                                <div style={{ padding: '20px', textAlign: 'center', color: 'var(--app-foreground-subtle)', fontSize: 13 }}>
                                                    {t('canvas.chat.model_selector.no_thinking_models')}
                                                </div>
                                            )}
                                            {modelTab === 'multimodal' && mode === 'fast' && filterMultimodalModelsForMode(availableMultimodalModels, mode).length === 0 && (
                                                <div style={{ padding: '20px', textAlign: 'center', color: 'var(--app-foreground-subtle)', fontSize: 13 }}>
                                                    {t('canvas.chat.model_selector.no_quick_models')}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div
                                onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                                onMouseEnter={() => setHoveredIcon('web_search')}
                                onMouseLeave={() => setHoveredIcon(null)}
                                style={{
                                    width: 36,
                                    height: 36,
                                    borderRadius: 100,
                                    backgroundColor: webSearchEnabled ? 'color-mix(in srgb, var(--app-primary) 10%, transparent)' : 'var(--app-control-track)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                    position: 'relative',
                                    border: webSearchEnabled ? '1px solid color-mix(in srgb, var(--app-primary) 22%, var(--app-border))' : '1px solid transparent'
                                }}>
                                <Globe size={18} color={webSearchEnabled ? 'var(--app-primary)' : 'var(--app-foreground-muted)'} />
                                {hoveredIcon === 'web_search' && (
                                    <div style={{
                                        position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)', marginBottom: 8,
                                        backgroundColor: 'var(--app-glass)', color: 'var(--app-foreground)', padding: '8px 12px', borderRadius: 12, width: 160, zIndex: 2000, border: '1px solid var(--app-border)', boxShadow: 'var(--app-shadow-panel)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)'
                                    }}>
                                        <div style={{ fontWeight: 600, fontSize: 13 }}>{t('canvas.chat.history.web_search')}</div>
                                        <div style={{ fontSize: 11, color: 'var(--app-foreground-muted)', marginTop: 2 }}>{t('canvas.chat.history.web_search_hint')}</div>
                                    </div>
                                )}
                            </div>

                            {/* Send / Stop button */}
                            <button
                                type="button"
                                aria-label={showStopButton
                                    ? t('canvas.chat.stop_response_aria', 'Stop agent response')
                                    : t('canvas.chat.send_message_aria', 'Send message')}
                                onClick={showStopButton ? stopStreaming : handleSend}
                                disabled={!showStopButton && (!hasInput || isBusy)}
                                style={{
                                    width: 38,
                                    height: 38,
                                    borderRadius: '50%',
                                    border: 'none',
                                    backgroundColor: showStopButton ? 'var(--app-danger)' : (hasInput && !isBusy ? 'var(--app-primary)' : 'var(--app-control)'),
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: (showStopButton || (hasInput && !isBusy)) ? 'pointer' : 'default',
                                    color: (showStopButton || (hasInput && !isBusy)) ? 'var(--app-primary-foreground)' : 'var(--app-foreground-subtle)',
                                    transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                                    boxShadow: (showStopButton || (hasInput && !isBusy))
                                        ? 'var(--app-shadow-control)'
                                        : 'none',
                                    transform: (showStopButton || (hasInput && !isBusy)) ? 'scale(1)' : 'scale(0.95)',
                                }}>
                                {showStopButton ? <Square size={16} fill="currentColor" /> : (isBusy ? <Loader2 size={18} style={{ animation: 'spin 1.5s linear infinite' }} /> : <ArrowUp size={20} strokeWidth={2.5} />)}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <AssetLibraryModal
                open={isForwardAssetLibraryOpen}
                onOpenChange={(open) => {
                    setIsForwardAssetLibraryOpen(open)
                    if (!open) {
                        setForwardMode(null)
                    }
                }}
                onImport={handleForwardAssetsSelected}
                isDark={isDark}
                mode="generator-pick"
                assetType="image"
                selectionMode="multiple"
                allowEmptySelection
                initialProject={{
                    project_id: projectId,
                    project_name: `Project ${projectId}`,
                    asset_count: 0,
                }}
                onSelect={handleForwardAssetsSelected}
            />

            <ImagePreviewDialog
                open={!!pendingAttachmentPreview}
                onOpenChange={(open) => {
                    if (!open) {
                        setPendingAttachmentPreview((current: any) => {
                            if (current?.ownedUrl) {
                                URL.revokeObjectURL(current.ownedUrl)
                            }
                            return null
                        })
                    }
                }}
                src={pendingAttachmentPreview?.src || null}
                alt={pendingAttachmentPreview?.alt || attachmentPreviewLabel}
                title={pendingAttachmentPreview?.alt || attachmentPreviewLabel}
                downloadUrl={pendingAttachmentPreview?.src || null}
            />

            <style>{`
                @keyframes slideIn {
                    from { transform: translateX(12px); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(12px); }
                }
                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
                @keyframes blink {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0; }
                }
                @keyframes slideUp {
                    from { opacity: 0; transform: translateY(8px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                [contenteditable][data-placeholder]:empty::before {
                    content: attr(data-placeholder);
                    color: var(--app-foreground-subtle);
                    pointer-events: none;
                    position: absolute;
                    top: 0;
                    left: 0;
                }
                [data-mention-id]:hover {
                    filter: brightness(1.1);
                    box-shadow: 0 2px 8px var(--app-focus-ring);
                }
            `}</style>
        </div>
    )
}

