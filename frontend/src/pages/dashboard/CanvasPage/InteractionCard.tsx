import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { MessageSquareMore, Send, Edit3, Check } from 'lucide-react'
import { useIsDarkMode } from '@/hooks/useTheme'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { InteractionField, InteractionOption, InteractionQuestion, PendingInteraction } from '@/api/endpoints/agent'
import { Button } from '@/components/ui/button'

interface InteractionCardProps {
    interaction: PendingInteraction
    fallbackContent?: string | null
    onRespond: (requestId: string, answer: string, displayLabel?: string, answers?: Record<string, any>) => void
    disabled?: boolean
}

type InteractionDisplayMode = 'buttons' | 'text_input' | 'cards' | 'color_picker'
type CanvasInteractionField = InteractionField & { default_value?: any; max_selections?: number | null; options?: InteractionOption[] }
type CanvasInteractionSchema = NonNullable<PendingInteraction['schema']> & {
    fields: CanvasInteractionField[]
}
type CanvasInteractionQuestion = InteractionQuestion & { maxSelections?: number | null; options?: InteractionOption[] }
type CanvasQuestionSchema = NonNullable<PendingInteraction['schema']> & {
    questions: CanvasInteractionQuestion[]
}

const OTHER_SELECTION_VALUE = '__ask_user_other__'

function hasSyntheticOtherOption(field: CanvasInteractionField): boolean {
    return (field.options || []).some((option) => (
        String(option.value || '').trim() === OTHER_SELECTION_VALUE
        || Boolean((option as Record<string, any>).is_custom_other ?? (option as Record<string, any>).isCustomOther)
    ))
}

function supportsCustomOther(field: CanvasInteractionField): boolean {
    return ['radio', 'cards', 'checkbox'].includes(String(field.type || '').trim())
        && !hasSyntheticOtherOption(field)
}

function isColorOption(option: InteractionOption): boolean {
    return /^#(?:[0-9a-fA-F]{3}){1,2}$/.test(String(option.value || '').trim())
}

function isSchemaAskUserInteraction(interaction: PendingInteraction): interaction is PendingInteraction & { schema: CanvasInteractionSchema } {
    return interaction.kind !== 'ask_user'
        && !!interaction.schema
        && Array.isArray(interaction.schema.fields)
        && interaction.schema.fields.length > 0
}

function isQuestionAskUserInteraction(interaction: PendingInteraction): interaction is PendingInteraction & { schema: CanvasQuestionSchema } {
    return interaction.kind === 'ask_user' && !!interaction.schema && Array.isArray(interaction.schema.questions) && interaction.schema.questions.length > 0
}

function getPrimaryField(interaction: PendingInteraction): InteractionField | null {
    const fields = interaction.schema?.fields
    return Array.isArray(fields) && fields.length > 0 ? fields[0] : null
}

function resolveDisplayMode(
    field: InteractionField | null,
    options: InteractionOption[],
): InteractionDisplayMode {
    const fieldType = String(field?.type || '').trim()

    if (fieldType === 'cards') {
        return options.length > 0 && options.every(isColorOption) ? 'color_picker' : 'cards'
    }
    if (fieldType === 'radio' || fieldType === 'checkbox' || fieldType === 'select') {
        return 'buttons'
    }
    return options.length > 0 ? 'buttons' : 'text_input'
}

function getDefaultFieldValue(field: CanvasInteractionField): any {
    return field.default_value !== undefined ? field.default_value : field.type === 'checkbox' ? [] : ''
}

function getDefaultQuestionValue(question: CanvasInteractionQuestion): any { return question.type === 'multiple' ? [] : '' }

function isQuestionRequired(question: CanvasInteractionQuestion): boolean {
    return question.required !== false
}

function buildInitialQuestionState(
    schema: CanvasQuestionSchema,
    answers: Record<string, any> | null | undefined,
): { formAnswers: Record<string, any>, otherAnswers: Record<string, string> } {
    const formAnswers: Record<string, any> = {}
    const otherAnswers: Record<string, string> = {}

    for (const question of schema.questions) {
        const answer = answers?.[question.id]
        if (answer === undefined) {
            formAnswers[question.id] = getDefaultQuestionValue(question)
            continue
        }
        if ((question.type === 'single' || question.type === 'input') && answer && typeof answer === 'object' && !Array.isArray(answer)) {
            const source = answer as Record<string, any>
            if (String(source.type || '').trim() === 'other') {
                formAnswers[question.id] = OTHER_SELECTION_VALUE
                otherAnswers[question.id] = String(source.value || '').trim()
            } else {
                formAnswers[question.id] = String(source.value || '').trim()
            }
            continue
        }
        if (question.type === 'multiple' && Array.isArray(answer)) {
            const nextValues: string[] = []
            answer.forEach((entry) => {
                if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
                    const source = entry as Record<string, any>
                    if (String(source.type || '').trim() === 'other') {
                        nextValues.push(OTHER_SELECTION_VALUE)
                        otherAnswers[question.id] = String(source.value || '').trim()
                        return
                    }
                    const optionValue = String(source.value || '').trim()
                    if (optionValue) {
                        nextValues.push(optionValue)
                    }
                    return
                }
                const normalized = String(entry || '').trim()
                if (normalized) {
                    nextValues.push(normalized)
                }
            })
            formAnswers[question.id] = nextValues
            continue
        }
        formAnswers[question.id] = answer
    }

    return { formAnswers, otherAnswers }
}

function buildInitialState(
    schema: CanvasInteractionSchema,
    answers: Record<string, any> | null | undefined,
): { formAnswers: Record<string, any>, otherAnswers: Record<string, string> } {
    const formAnswers: Record<string, any> = {}
    const otherAnswers: Record<string, string> = {}

    for (const field of schema.fields) {
        const answer = answers?.[field.id]
        if (answer === undefined) {
            formAnswers[field.id] = getDefaultFieldValue(field)
            continue
        }

        if ((field.type === 'radio' || field.type === 'cards') && answer && typeof answer === 'object' && !Array.isArray(answer)) {
            const source = answer as Record<string, any>
            if (String(source.type || '').trim() === 'other') {
                formAnswers[field.id] = OTHER_SELECTION_VALUE
                otherAnswers[field.id] = String(source.value || '').trim()
            } else {
                formAnswers[field.id] = String(source.value || '').trim()
            }
            continue
        }

        if (field.type === 'checkbox' && Array.isArray(answer)) {
            const nextValues: string[] = []
            answer.forEach((entry) => {
                if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
                    const source = entry as Record<string, any>
                    if (String(source.type || '').trim() === 'other') {
                        nextValues.push(OTHER_SELECTION_VALUE)
                        otherAnswers[field.id] = String(source.value || '').trim()
                        return
                    }
                    const optionValue = String(source.value || '').trim()
                    if (optionValue) {
                        nextValues.push(optionValue)
                    }
                    return
                }
                const normalized = String(entry || '').trim()
                if (normalized) {
                    nextValues.push(normalized)
                }
            })
            formAnswers[field.id] = nextValues
            continue
        }

        formAnswers[field.id] = typeof answer === 'string'
            ? answer
            : (answer && typeof answer === 'object' && !Array.isArray(answer))
                ? String((answer as Record<string, any>).value || '').trim()
                : answer
    }

    return { formAnswers, otherAnswers }
}

function getOptionLabel(field: CanvasInteractionField, value: string): string {
    return (field.options || []).find((option) => option.value === value)?.label || value
}

function formatAnswerForDisplay(field: CanvasInteractionField, value: unknown): string {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        const source = value as Record<string, any>
        return String(source.label || source.value || '').trim()
    }
    if (Array.isArray(value)) {
        return value
            .map((entry) => {
                if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
                    const source = entry as Record<string, any>
                    return String(source.label || source.value || '').trim()
                }
                return getOptionLabel(field, String(entry || '').trim())
            })
            .filter(Boolean)
            .join(' / ')
    }
    const text = String(value ?? '').trim()
    if (!text) {
        return ''
    }
    if (field.type === 'radio' || field.type === 'select' || field.type === 'cards' || field.type === 'checkbox') {
        return getOptionLabel(field, text)
    }
    return text
}

function buildDisplayLabel(schema: CanvasInteractionSchema, answers: Record<string, any>): string {
    const values = schema.fields
        .map((field) => formatAnswerForDisplay(field, answers[field.id]))
        .filter(Boolean)
    return values.join(' / ') || schema.title
}

function buildSubmitAnswers(
    schema: CanvasInteractionSchema,
    formAnswers: Record<string, any>,
    otherAnswers: Record<string, string>,
    t: (key: string, fallback?: string) => string,
): Record<string, any> {
    const submitAnswers: Record<string, any> = {}

    for (const field of schema.fields) {
        const value = formAnswers[field.id]
        if (field.type === 'radio' || field.type === 'cards') {
            if (value === OTHER_SELECTION_VALUE) {
                const otherValue = String(otherAnswers[field.id] || '').trim()
                const otherLabel = String(field.other_label || t('canvas.chat.interaction.other', 'Other')).trim()
                submitAnswers[field.id] = {
                    type: 'other',
                    value: otherValue,
                    label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
                }
                continue
            }
            submitAnswers[field.id] = {
                type: 'option',
                value: String(value || '').trim(),
                label: getOptionLabel(field, String(value || '').trim()),
            }
            continue
        }
        if (field.type === 'checkbox') {
            const selectedValues = Array.isArray(value) ? value : []
            submitAnswers[field.id] = selectedValues
                .map((entry) => {
                    if (entry === OTHER_SELECTION_VALUE) {
                        const otherValue = String(otherAnswers[field.id] || '').trim()
                        const otherLabel = String(field.other_label || t('canvas.chat.interaction.other', 'Other')).trim()
                        return {
                            type: 'other',
                            value: otherValue,
                            label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
                        }
                    }
                    const normalized = String(entry || '').trim()
                    if (!normalized) {
                        return null
                    }
                    return normalized
                })
                .filter(Boolean)
            continue
        }
        submitAnswers[field.id] = value
    }

    return submitAnswers
}

function getQuestionOptionLabel(question: CanvasInteractionQuestion, value: string): string {
    return (question.options || []).find((option) => option.value === value)?.label || value
}

function formatQuestionAnswerForDisplay(question: CanvasInteractionQuestion, value: unknown): string {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        const source = value as Record<string, any>
        return String(source.label || source.value || '').trim()
    }
    if (Array.isArray(value)) {
        return value
            .map((entry) => {
                if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
                    const source = entry as Record<string, any>
                    return String(source.label || source.value || '').trim()
                }
                return getQuestionOptionLabel(question, String(entry || '').trim())
            })
            .filter(Boolean)
            .join(' / ')
    }
    const text = String(value ?? '').trim()
    return text ? getQuestionOptionLabel(question, text) : ''
}

function buildQuestionDisplayLabel(schema: CanvasQuestionSchema, answers: Record<string, any>): string {
    const values = schema.questions.map((question) => formatQuestionAnswerForDisplay(question, answers[question.id])).filter(Boolean)
    return values.join(' / ') || schema.title
}

function buildQuestionSubmitAnswers(
    schema: CanvasQuestionSchema,
    formAnswers: Record<string, any>,
    otherAnswers: Record<string, string>,
    t: (key: string, fallback?: string) => string,
): Record<string, any> {
    const submitAnswers: Record<string, any> = {}

    for (const question of schema.questions) {
        const value = formAnswers[question.id]
        if (question.type === 'input') { const normalized = String(value || '').trim(); submitAnswers[question.id] = { type: 'input', value: normalized, label: normalized }; continue }
        if (question.type === 'multiple') {
            const selectedValues = Array.isArray(value) ? value : []
            submitAnswers[question.id] = selectedValues
                .map((entry) => {
                    if (entry === OTHER_SELECTION_VALUE) {
                        const otherValue = String(otherAnswers[question.id] || '').trim()
                        const otherLabel = String(t('canvas.chat.interaction.other', 'Other')).trim()
                        return {
                            type: 'other',
                            value: otherValue,
                            label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
                        }
                    }
                    const normalized = String(entry || '').trim()
                    if (!normalized) {
                        return null
                    }
                    return {
                        type: 'option',
                        value: normalized,
                        label: getQuestionOptionLabel(question, normalized),
                    }
                })
                .filter(Boolean)
            continue
        }
        if (value === OTHER_SELECTION_VALUE) {
            const otherValue = String(otherAnswers[question.id] || '').trim()
            const otherLabel = String(t('canvas.chat.interaction.other', 'Other')).trim()
            submitAnswers[question.id] = {
                type: 'other',
                value: otherValue,
                label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
            }
            continue
        }
        const normalized = String(value || '').trim()
        submitAnswers[question.id] = {
            type: 'option',
            value: normalized,
            label: getQuestionOptionLabel(question, normalized),
        }
    }

    return submitAnswers
}

function resolveLegacySubmittedSelection(interaction: PendingInteraction): { value: string | null, label: string } {
    const primaryField = getPrimaryField(interaction) as CanvasInteractionField | null
    if (!primaryField || !interaction.answers || typeof interaction.answers !== 'object') {
        return { value: null, label: '' }
    }

    const fieldId = String(primaryField.id || 'response').trim() || 'response'
    const answer = (interaction.answers as Record<string, any>)[fieldId]

    if (answer && typeof answer === 'object' && !Array.isArray(answer)) {
        const source = answer as Record<string, any>
        const value = String(source.value || '').trim()
        return {
            value: value || null,
            label: formatAnswerForDisplay(primaryField, source),
        }
    }

    if (Array.isArray(answer)) {
        return {
            value: null,
            label: formatAnswerForDisplay(primaryField, answer),
        }
    }

    const value = String(answer ?? '').trim()
    if (!value) {
        return { value: null, label: '' }
    }

    return {
        value,
        label: formatAnswerForDisplay(primaryField, value),
    }
}

export function InteractionCard({ interaction, fallbackContent, onRespond, disabled }: InteractionCardProps) {
    const isDark = useIsDarkMode()
    const { t } = useTranslation()
    const translateWithFallback = (key: string, fallback?: string) => (
        fallback === undefined ? t(key) : t(key, fallback)
    )

    const isQuestionAskUser = isQuestionAskUserInteraction(interaction)
    const questionSchema = isQuestionAskUser ? interaction.schema : null
    const isSchemaAskUser = isSchemaAskUserInteraction(interaction)
    const schema = isSchemaAskUser ? interaction.schema : null
    const initialState = useMemo(
        () => {
            if (questionSchema) {
                return buildInitialQuestionState(questionSchema, interaction.answers)
            }
            if (schema) {
                return buildInitialState(schema, interaction.answers)
            }
            return { formAnswers: {}, otherAnswers: {} }
        },
        [interaction.answers, questionSchema, schema],
    )
    const [formAnswers, setFormAnswers] = useState<Record<string, any>>(() => initialState.formAnswers)
    const [otherAnswers, setOtherAnswers] = useState<Record<string, string>>(() => initialState.otherAnswers)
    const initialStateKey = useMemo(() => JSON.stringify(initialState), [initialState])
    const lastSyncedStateKeyRef = useRef(`${String(interaction.request_id || '').trim()}:${initialStateKey}`)

    useEffect(() => {
        const syncKey = `${String(interaction.request_id || '').trim()}:${initialStateKey}`
        if (lastSyncedStateKeyRef.current === syncKey) {
            return
        }
        lastSyncedStateKeyRef.current = syncKey
        setFormAnswers(initialState.formAnswers)
        setOtherAnswers(initialState.otherAnswers)
    }, [initialState, initialStateKey, interaction.request_id])

    const legacySubmittedSelection = useMemo(
        () => resolveLegacySubmittedSelection(interaction),
        [interaction],
    )
    const legacySelectionKey = useMemo(
        () => JSON.stringify(legacySubmittedSelection),
        [legacySubmittedSelection],
    )
    const lastLegacySelectionKeyRef = useRef(`${String(interaction.request_id || '').trim()}:${legacySelectionKey}`)
    const [selectedValue, setSelectedValue] = useState<string | null>(() => legacySubmittedSelection.value)
    const [selectedLabel, setSelectedLabel] = useState<string>(() => legacySubmittedSelection.label)
    const [showOtherInput, setShowOtherInput] = useState(false)
    const [otherText, setOtherText] = useState('')

    useEffect(() => {
        const syncKey = `${String(interaction.request_id || '').trim()}:${legacySelectionKey}`
        if (lastLegacySelectionKeyRef.current === syncKey) {
            return
        }
        lastLegacySelectionKeyRef.current = syncKey
        setSelectedValue(legacySubmittedSelection.value)
        setSelectedLabel(legacySubmittedSelection.label)
        setShowOtherInput(false)
        setOtherText('')
    }, [interaction.request_id, legacySelectionKey, legacySubmittedSelection])

    const shellStyle: CSSProperties = {
        width: '100%',
        margin: '8px 0',
        borderRadius: 18,
        border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
        background: isDark ? 'var(--app-glass)' : 'var(--app-glass)',
        boxShadow: isDark ? 'var(--app-shadow-panel)' : 'var(--app-shadow-panel)',
        backdropFilter: 'blur(18px)',
        WebkitBackdropFilter: 'blur(18px)',
        overflow: 'hidden',
        transition: 'all 0.24s ease',
    }
    const fieldSurfaceStyle: CSSProperties = {
        width: '100%',
        padding: '10px 12px',
        borderRadius: 14,
        border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
        background: isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)',
        color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
        boxShadow: isDark ? 'var(--app-shadow-selected)' : 'var(--app-shadow-selected)',
        fontSize: 13,
        outline: 'none',
    }
    const selectedTint = isDark ? 'var(--app-focus-ring)' : 'var(--app-focus-ring)'
    const accentBorder = isDark ? 'var(--app-focus-ring)' : 'var(--app-focus-ring)'
    const mutedBorder = isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'
    const subtleSurface = 'var(--app-surface-muted)'
    const summaryLabel = selectedLabel || selectedValue || ''
    const compactChoiceGroupStyle: CSSProperties = {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
    }
    const buildSelectionRowStyle = (
        selected: boolean,
        options?: {
            dashed?: boolean
            card?: boolean
            fullWidth?: boolean
            compact?: boolean
        },
    ): CSSProperties => ({
        width: options?.fullWidth ? '100%' : 'fit-content',
        maxWidth: '100%',
        minHeight: options?.compact ? 42 : 56,
        padding: options?.card ? '14px 16px' : (options?.compact ? '8px 14px' : '12px 16px'),
        borderRadius: options?.card ? 14 : 12,
        border: selected
            ? `1px solid ${accentBorder}`
            : options?.dashed
                ? '1px dashed var(--app-border-strong)'
                : `1px solid ${mutedBorder}`,
        background: selected
            ? selectedTint
            : (options?.card ? subtleSurface : 'transparent'),
        color: selected ? 'var(--app-primary)' : (isDark ? 'var(--app-foreground)' : 'var(--app-foreground)'),
        cursor: disabled ? 'default' : 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: selected
            ? (isDark ? 'var(--app-shadow-control)' : 'var(--app-shadow-control)')
            : 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        textAlign: 'left',
        fontSize: 13,
        fontWeight: 600,
    })

    const hasLegacyAskUserFields = interaction.kind === 'ask_user' && !questionSchema && Array.isArray(interaction.schema?.fields) && interaction.schema.fields.length > 0

    if (hasLegacyAskUserFields && interaction.schema) {
        return (
            <div data-testid="interaction-card-shell" style={shellStyle}>
                <div style={{ padding: '14px 16px' }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                        {interaction.schema.title}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.6, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                        {t('home.interaction.legacyAskUserUnsupported', 'This question was created by an older interaction format and cannot be continued. Please start a new request.')}
                    </div>
                </div>
            </div>
        )
    }

    if (questionSchema) {
        const requestId = String(interaction.request_id || '').trim()
        if (!requestId) {
            return null
        }

        const explicitBriefing = String(interaction.content || '').trim()
        const fallbackQuestionBriefing = !explicitBriefing
            && interaction.question
            && interaction.question !== questionSchema.title
            ? String(interaction.question).trim()
            : ''
        const fallbackMessageBriefing = !explicitBriefing
            && !fallbackQuestionBriefing
            && typeof fallbackContent === 'string'
            && fallbackContent.trim() !== questionSchema.title
            ? fallbackContent.trim()
            : ''
        const briefing = explicitBriefing || fallbackQuestionBriefing || fallbackMessageBriefing
        const description = String(!briefing ? (questionSchema.description || '') : '').trim()
        const canSubmit = questionSchema.questions.every((askQuestion) => {
            const value = formAnswers[askQuestion.id]
            if (askQuestion.type === 'input') {
                return !isQuestionRequired(askQuestion) || String(value ?? '').trim().length > 0
            }
            if (askQuestion.type === 'multiple') {
                const selectedValues = Array.isArray(value) ? value : []
                if (selectedValues.length === 0) {
                    return false
                }
                if (selectedValues.includes(OTHER_SELECTION_VALUE)) {
                    return String(otherAnswers[askQuestion.id] || '').trim().length > 0
                }
                return true
            }
            if (value === OTHER_SELECTION_VALUE) {
                return String(otherAnswers[askQuestion.id] || '').trim().length > 0
            }
            return String(value ?? '').trim().length > 0
        })

        const submitQuestionAnswers = () => {
            if (disabled || !canSubmit) {
                return
            }
            const submitAnswers = buildQuestionSubmitAnswers(questionSchema, formAnswers, otherAnswers, translateWithFallback)
            onRespond(requestId, JSON.stringify(submitAnswers), buildQuestionDisplayLabel(questionSchema, submitAnswers), submitAnswers)
        }

        return (
            <div data-testid="interaction-card-shell" style={shellStyle}>
                <div style={{ padding: '14px 16px 0' }}>
                    {briefing ? (
                        <div style={{
                            fontSize: 13,
                            color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground)',
                            lineHeight: 1.65,
                            marginBottom: 12,
                        }}>
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                    table: ({ children }) => <div style={{ overflowX: 'auto', margin: '8px 0' }}><table style={{ width: '100%', borderCollapse: 'collapse', borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)', fontSize: 13 }}>{children}</table></div>,
                                    th: ({ children }) => <th style={{ padding: '8px 10px', borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)', textAlign: 'left', fontWeight: 600 }}>{children}</th>,
                                    td: ({ children }) => <td style={{ padding: '8px 10px', borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)' }}>{children}</td>,
                                }}
                            >
                                {briefing}
                            </ReactMarkdown>
                        </div>
                    ) : (
                        <div style={{ fontSize: 14, fontWeight: 600, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                            {questionSchema.title}
                        </div>
                    )}
                    {description ? (
                        <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.6, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                            {description}
                        </div>
                    ) : null}
                </div>

                <div style={{ padding: '12px 16px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {questionSchema.questions.map((askQuestion) => {
                        const currentValue = formAnswers[askQuestion.id]
                        const selectedValues = Array.isArray(currentValue) ? currentValue as string[] : []
                        const maxSelections = askQuestion.max_selections ?? null
                        const maxReached = askQuestion.type === 'multiple'
                            && typeof maxSelections === 'number'
                            && selectedValues.length >= maxSelections
                        const isOtherSelected = askQuestion.type === 'multiple'
                            ? selectedValues.includes(OTHER_SELECTION_VALUE)
                            : currentValue === OTHER_SELECTION_VALUE

                        return (
                            <div key={askQuestion.id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                <div>
                                    <div style={{
                                        fontSize: 11,
                                        fontWeight: 700,
                                        color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)',
                                        textTransform: 'uppercase',
                                    }}>
                                        {askQuestion.header}
                                    </div>
                                    <div style={{ marginTop: 3, fontSize: 13, fontWeight: 600, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                                        {askQuestion.question}
                                    </div>
                                </div>
                                <div style={compactChoiceGroupStyle}>
                                    {askQuestion.type === 'input' ? (
                                        <input id={`${requestId}-${askQuestion.id}`} aria-label={askQuestion.question} value={String(currentValue ?? '')} disabled={disabled} placeholder={t('canvas.chat.interaction.other_placeholder', 'Type your response...')} onChange={(event) => setFormAnswers((current) => ({ ...current, [askQuestion.id]: event.target.value }))} style={fieldSurfaceStyle} />
                                    ) : null}
                                    {askQuestion.type !== 'input' ? (askQuestion.options || []).map((option) => {
                                        const selected = askQuestion.type === 'multiple'
                                            ? selectedValues.includes(option.value)
                                            : String(currentValue ?? '') === option.value
                                        const optionDisabled = disabled || (askQuestion.type === 'multiple' && maxReached && !selected)
                                        return (
                                            <button
                                                key={`${askQuestion.id}-${option.value}`}
                                                type="button"
                                                aria-label={option.label}
                                                disabled={optionDisabled}
                                                onClick={() => {
                                                    if (askQuestion.type === 'multiple') {
                                                        setFormAnswers((current) => {
                                                            const existing = Array.isArray(current[askQuestion.id]) ? current[askQuestion.id] as string[] : []
                                                            const next = existing.includes(option.value)
                                                                ? existing.filter((value) => value !== option.value)
                                                                : [...existing, option.value]
                                                            return { ...current, [askQuestion.id]: next }
                                                        })
                                                        return
                                                    }
                                                    setFormAnswers((current) => ({ ...current, [askQuestion.id]: option.value }))
                                                }}
                                                style={{
                                                    ...buildSelectionRowStyle(selected, {
                                                        compact: askQuestion.type === 'multiple',
                                                        fullWidth: askQuestion.type === 'single',
                                                    }),
                                                    opacity: optionDisabled ? 0.6 : 1,
                                                    ...(option.description
                                                        ? {
                                                            flexDirection: 'column' as const,
                                                            alignItems: 'flex-start' as const,
                                                            gap: 4,
                                                        }
                                                        : {}),
                                                }}
                                            >
                                                <div style={{
                                                    width: '100%',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'space-between',
                                                    gap: 8,
                                                }}>
                                                    <span>{option.label}</span>
                                                    {selected ? <Check size={14} /> : null}
                                                </div>
                                                {option.description ? (
                                                    <div style={{ fontSize: 12, fontWeight: 400, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                                                        {option.description}
                                                    </div>
                                                ) : null}
                                            </button>
                                        )
                                    }) : null}
                                    {askQuestion.type !== 'input' ? (
                                        <button
                                        type="button"
                                        aria-label={t('canvas.chat.interaction.other', 'Other')}
                                        disabled={disabled || (askQuestion.type === 'multiple' && maxReached && !isOtherSelected)}
                                        onClick={() => {
                                            if (askQuestion.type === 'multiple') {
                                                setFormAnswers((current) => {
                                                    const existing = Array.isArray(current[askQuestion.id]) ? current[askQuestion.id] as string[] : []
                                                    const next = existing.includes(OTHER_SELECTION_VALUE)
                                                        ? existing.filter((value) => value !== OTHER_SELECTION_VALUE)
                                                        : [...existing, OTHER_SELECTION_VALUE]
                                                    return { ...current, [askQuestion.id]: next }
                                                })
                                                return
                                            }
                                            setFormAnswers((current) => ({ ...current, [askQuestion.id]: OTHER_SELECTION_VALUE }))
                                        }}
                                        style={{
                                            ...buildSelectionRowStyle(isOtherSelected, {
                                                dashed: true,
                                                compact: askQuestion.type === 'multiple',
                                                fullWidth: askQuestion.type === 'single',
                                            }),
                                            opacity: disabled || (askQuestion.type === 'multiple' && maxReached && !isOtherSelected) ? 0.6 : 1,
                                            justifyContent: 'flex-start',
                                            color: isOtherSelected ? 'var(--app-primary)' : (isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)'),
                                        }}
                                    >
                                        <Edit3 size={12} />
                                        <span>{t('canvas.chat.interaction.other', 'Other')}</span>
                                        {isOtherSelected ? <Check size={14} /> : null}
                                        </button>
                                    ) : null}
                                </div>
                                {isOtherSelected ? (
                                    <input
                                        id={`${requestId}-${askQuestion.id}-other`}
                                        aria-label={askQuestion.question}
                                        value={otherAnswers[askQuestion.id] || ''}
                                        disabled={disabled}
                                        placeholder={t('canvas.chat.interaction.other_placeholder', 'Type your response...')}
                                        onChange={(event) => setOtherAnswers((current) => ({ ...current, [askQuestion.id]: event.target.value }))}
                                        style={fieldSurfaceStyle}
                                    />
                                ) : null}
                            </div>
                        )
                    })}

                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <Button
                            type="button"
                            size="sm"
                            disabled={disabled || !canSubmit}
                            onClick={() => submitQuestionAnswers()}
                        >
                            <Check className="h-4 w-4" aria-hidden="true" />
                            {questionSchema.submit_label || t('home.interaction.continue', 'Submit')}
                        </Button>
                    </div>
                </div>
            </div>
        )
    }

    const handleSelect = (value: string, label?: string) => {
        if (disabled) return
        setSelectedValue(value)
        setSelectedLabel(label || value)
        setShowOtherInput(false)
        onRespond(interaction.request_id, value, label)
    }

    const handleOtherClick = () => {
        if (disabled) return
        setShowOtherInput(true)
    }

    const handleOtherSubmit = () => {
        if (disabled || !otherText.trim()) return
        const normalized = otherText.trim()
        setSelectedValue(normalized)
        setSelectedLabel(normalized)
        setShowOtherInput(false)
        onRespond(interaction.request_id, normalized)
    }

    if (isSchemaAskUser && schema) {
        const requestId = String(interaction.request_id || '').trim()
        if (!requestId) {
            return null
        }

        const explicitBriefing = String(interaction.content || '').trim()
        const fallbackQuestionBriefing = !explicitBriefing
            && interaction.question
            && interaction.question !== schema.title
            ? String(interaction.question).trim()
            : ''
        const fallbackMessageBriefing = !explicitBriefing
            && !fallbackQuestionBriefing
            && typeof fallbackContent === 'string'
            && fallbackContent.trim() !== schema.title
            ? fallbackContent.trim()
            : ''
        const briefing = explicitBriefing || fallbackQuestionBriefing || fallbackMessageBriefing
        const description = String(!briefing ? (schema.description || '') : '').trim()

        const canSubmit = schema.fields.every((field) => {
            if (!field.required) {
                return true
            }
            const value = formAnswers[field.id]
            if (field.type === 'checkbox') {
                const selectedValues = Array.isArray(value) ? value : []
                if (selectedValues.length === 0) {
                    return false
                }
                if (selectedValues.includes(OTHER_SELECTION_VALUE)) {
                    return String(otherAnswers[field.id] || '').trim().length > 0
                }
                return true
            }
            if (supportsCustomOther(field) && value === OTHER_SELECTION_VALUE) {
                return String(otherAnswers[field.id] || '').trim().length > 0
            }
            return String(value ?? '').trim().length > 0
        })

        const handleSubmit = () => {
            if (disabled || !canSubmit) {
                return
            }
            const submitAnswers = buildSubmitAnswers(schema, formAnswers, otherAnswers, translateWithFallback)
            onRespond(requestId, JSON.stringify(submitAnswers), buildDisplayLabel(schema, submitAnswers), submitAnswers)
        }

        return (
            <div data-testid="interaction-card-shell" style={shellStyle}>
                <div style={{ padding: '14px 16px 0' }}>
                    {briefing ? (
                        <div style={{
                            fontSize: 13,
                            color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground)',
                            lineHeight: 1.65,
                            marginBottom: 12,
                        }}>
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                    h1: ({ children }) => <h1 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 10px', color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>{children}</h1>,
                                    h2: ({ children }) => <h2 style={{ fontSize: 17, fontWeight: 700, margin: '0 0 8px', color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>{children}</h2>,
                                    h3: ({ children }) => <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 8px', color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>{children}</h3>,
                                    p: ({ children }) => <p style={{ margin: '0 0 8px' }}>{children}</p>,
                                    ul: ({ children }) => <ul style={{ margin: '0 0 8px', paddingLeft: 18 }}>{children}</ul>,
                                    ol: ({ children }) => <ol style={{ margin: '0 0 8px', paddingLeft: 18 }}>{children}</ol>,
                                    li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
                                    strong: ({ children }) => <strong style={{ fontWeight: 700, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>{children}</strong>,
                                    code: ({ children }) => (
                                        <code style={{
                                            padding: '1px 4px',
                                            borderRadius: 6,
                                            background: isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)',
                                            fontSize: 12,
                                        }}>{children}</code>
                                    ),
                                    pre: ({ children }) => <>{children}</>,
                                    table: ({ children }) => (
                                        <div style={{ overflowX: 'auto', margin: '8px 0' }}>
                                            <table style={{
                                                width: '100%',
                                                borderCollapse: 'collapse',
                                                borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)',
                                                fontSize: 13,
                                            }}>{children}</table>
                                        </div>
                                    ),
                                    th: ({ children }) => (
                                        <th style={{
                                            padding: '8px 10px',
                                            borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)',
                                            textAlign: 'left',
                                            fontWeight: 600,
                                        }}>{children}</th>
                                    ),
                                    td: ({ children }) => (
                                        <td style={{
                                            padding: '8px 10px',
                                            borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)',
                                        }}>{children}</td>
                                    ),
                                }}
                            >
                                {briefing}
                            </ReactMarkdown>
                        </div>
                    ) : (
                        <div style={{ fontSize: 14, fontWeight: 600, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                            {schema.title}
                        </div>
                    )}
                    {description ? (
                        <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.6, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                            {description}
                        </div>
                    ) : null}
                </div>

                <div style={{ padding: '12px 16px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {schema.fields.map((field) => {
                        const currentValue = formAnswers[field.id]

                        return (
                            <div key={field.id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                <label
                                    htmlFor={`${requestId}-${field.id}`}
                                    style={{
                                        fontSize: 13,
                                        fontWeight: 600,
                                        color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                                    }}
                                >
                                    {field.label}
                                    {field.required ? <span style={{ color: 'var(--app-danger)', marginLeft: 4 }}>*</span> : null}
                                </label>

                                {field.type === 'text' ? (
                                    <input
                                        id={`${requestId}-${field.id}`}
                                        aria-label={field.label}
                                        value={String(currentValue ?? '')}
                                        disabled={disabled}
                                        placeholder={field.placeholder || ''}
                                        onChange={(event) => setFormAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                                        style={fieldSurfaceStyle}
                                    />
                                ) : null}

                                {field.type === 'textarea' ? (
                                    <textarea
                                        id={`${requestId}-${field.id}`}
                                        aria-label={field.label}
                                        value={String(currentValue ?? '')}
                                        disabled={disabled}
                                        placeholder={field.placeholder || ''}
                                        rows={4}
                                        onChange={(event) => setFormAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                                        style={{ ...fieldSurfaceStyle, resize: 'vertical', minHeight: 88 }}
                                    />
                                ) : null}

                                {field.type === 'select' ? (
                                    <select
                                        id={`${requestId}-${field.id}`}
                                        aria-label={field.label}
                                        value={String(currentValue ?? '')}
                                        disabled={disabled}
                                        onChange={(event) => setFormAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                                        style={fieldSurfaceStyle}
                                    >
                                        <option value="">{field.placeholder || t('home.interaction.selectPlaceholder', 'Select')}</option>
                                        {(field.options || []).map((option) => (
                                            <option key={`${field.id}-${option.value}`} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                ) : null}

                                {(field.type === 'radio' || field.type === 'cards') ? (
                                    <div style={{
                                        ...(field.type === 'cards'
                                            ? {
                                                display: 'grid',
                                                gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                                                gap: 10,
                                            }
                                            : compactChoiceGroupStyle),
                                    }}>
                                        {(field.options || []).map((option) => {
                                            const selected = String(currentValue ?? '') === option.value

                                            if (field.type === 'cards' && isColorOption(option)) {
                                                return (
                                                    <button
                                                        key={`${field.id}-${option.value}`}
                                                        type="button"
                                                        aria-label={option.label}
                                                        disabled={disabled}
                                                        onClick={() => setFormAnswers((current) => ({ ...current, [field.id]: option.value }))}
                                                        style={{
                                                            width: 42,
                                                            height: 42,
                                                            padding: 0,
                                                            borderRadius: 14,
                                                            backgroundColor: option.value,
                                                            border: selected ? '3px solid var(--app-primary)' : '2px solid var(--app-border)',
                                                            boxShadow: isDark ? 'var(--app-shadow-control)' : 'var(--app-shadow-control)',
                                                            cursor: disabled ? 'default' : 'pointer',
                                                        }}
                                                        title={option.label}
                                                    />
                                                )
                                            }

                                            return (
                                                <button
                                                    key={`${field.id}-${option.value}`}
                                                    type="button"
                                                    aria-label={option.label}
                                                    disabled={disabled}
                                                    onClick={() => setFormAnswers((current) => ({ ...current, [field.id]: option.value }))}
                                                    style={{
                                                        ...buildSelectionRowStyle(selected, {
                                                            card: field.type === 'cards',
                                                            fullWidth: field.type === 'cards',
                                                            compact: field.type !== 'cards',
                                                        }),
                                                        ...(field.type === 'cards' || Boolean(option.description)
                                                            ? {
                                                                flexDirection: 'column' as const,
                                                                alignItems: 'flex-start' as const,
                                                                gap: 4,
                                                            }
                                                            : {}),
                                                    }}
                                                >
                                                    <div style={{
                                                        width: '100%',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'space-between',
                                                        gap: 8,
                                                        fontSize: 13,
                                                        fontWeight: 600,
                                                    }}>
                                                        <span>{option.label}</span>
                                                        {selected ? <Check size={14} /> : null}
                                                    </div>
                                                    {option.description ? (
                                                        <div style={{ fontSize: 12, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                                                            {option.description}
                                                        </div>
                                                    ) : null}
                                                </button>
                                            )
                                        })}

                                        {supportsCustomOther(field) ? (
                                            <button
                                                type="button"
                                                aria-label={field.other_label || t('canvas.chat.interaction.other', 'Other')}
                                                disabled={disabled}
                                                onClick={() => setFormAnswers((current) => ({ ...current, [field.id]: OTHER_SELECTION_VALUE }))}
                                                style={{
                                                    ...buildSelectionRowStyle(formAnswers[field.id] === OTHER_SELECTION_VALUE, {
                                                        dashed: true,
                                                        card: field.type === 'cards',
                                                        fullWidth: field.type === 'cards',
                                                        compact: field.type !== 'cards',
                                                    }),
                                                    gap: field.type === 'cards' ? 12 : 6,
                                                    justifyContent: 'flex-start',
                                                    color: formAnswers[field.id] === OTHER_SELECTION_VALUE
                                                        ? 'var(--app-primary)'
                                                        : (isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)'),
                                                }}
                                            >
                                                <Edit3 size={12} />
                                                <span>{field.other_label || t('canvas.chat.interaction.other', 'Other')}</span>
                                            </button>
                                        ) : null}
                                    </div>
                                ) : null}

                                {(field.type === 'radio' || field.type === 'cards') && supportsCustomOther(field) && currentValue === OTHER_SELECTION_VALUE ? (
                                    <input
                                        id={`${requestId}-${field.id}-other`}
                                        aria-label={field.label}
                                        value={otherAnswers[field.id] || ''}
                                        disabled={disabled}
                                        placeholder={field.other_placeholder || field.placeholder || t('canvas.chat.interaction.other_placeholder')}
                                        onChange={(event) => setOtherAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                                        style={fieldSurfaceStyle}
                                    />
                                ) : null}

                                {field.type === 'checkbox' ? (
                                    <div style={compactChoiceGroupStyle}>
                                        {(field.options || []).map((option) => {
                                            const selectedValues = Array.isArray(currentValue) ? currentValue as string[] : []
                                            const selected = selectedValues.includes(option.value)
                                            return (
                                                <button
                                                    key={`${field.id}-${option.value}`}
                                                    type="button"
                                                    aria-label={option.label}
                                                    disabled={disabled}
                                                    onClick={() => setFormAnswers((current) => {
                                                        const existing = Array.isArray(current[field.id]) ? current[field.id] as string[] : []
                                                        const next = existing.includes(option.value)
                                                            ? existing.filter((value) => value !== option.value)
                                                            : [...existing, option.value]
                                                        return { ...current, [field.id]: next }
                                                    })}
                                                    style={buildSelectionRowStyle(selected, { compact: true })}
                                                >
                                                    <span>{option.label}</span>
                                                    {selected ? <Check size={14} /> : null}
                                                </button>
                                            )
                                        })}
                                        {supportsCustomOther(field) ? (
                                            <button
                                                type="button"
                                                aria-label={field.other_label || t('canvas.chat.interaction.other', 'Other')}
                                                disabled={disabled}
                                                onClick={() => setFormAnswers((current) => {
                                                    const existing = Array.isArray(current[field.id]) ? current[field.id] as string[] : []
                                                    const next = existing.includes(OTHER_SELECTION_VALUE)
                                                        ? existing.filter((value) => value !== OTHER_SELECTION_VALUE)
                                                        : [...existing, OTHER_SELECTION_VALUE]
                                                    return { ...current, [field.id]: next }
                                                })}
                                                style={{
                                                    ...buildSelectionRowStyle(
                                                        Array.isArray(currentValue) && (currentValue as string[]).includes(OTHER_SELECTION_VALUE),
                                                        { dashed: true, compact: true },
                                                    ),
                                                    color: Array.isArray(currentValue) && (currentValue as string[]).includes(OTHER_SELECTION_VALUE)
                                                        ? 'var(--app-primary)'
                                                        : (isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)'),
                                                }}
                                            >
                                                <span>{field.other_label || t('canvas.chat.interaction.other', 'Other')}</span>
                                                {Array.isArray(currentValue) && (currentValue as string[]).includes(OTHER_SELECTION_VALUE) ? <Check size={14} /> : null}
                                            </button>
                                        ) : null}
                                    </div>
                                ) : null}

                                {field.type === 'checkbox' && supportsCustomOther(field) && Array.isArray(currentValue) && currentValue.includes(OTHER_SELECTION_VALUE) ? (
                                    <input
                                        id={`${requestId}-${field.id}-other`}
                                        aria-label={field.label}
                                        value={otherAnswers[field.id] || ''}
                                        disabled={disabled}
                                        placeholder={field.other_placeholder || field.placeholder || t('canvas.chat.interaction.other_placeholder')}
                                        onChange={(event) => setOtherAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                                        style={fieldSurfaceStyle}
                                    />
                                ) : null}
                            </div>
                        )
                    })}

                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                            type="button"
                            disabled={disabled || !canSubmit}
                            onClick={handleSubmit}
                            style={{
                                padding: '8px 14px',
                                borderRadius: 12,
                                border: `1px solid ${disabled || !canSubmit ? mutedBorder : accentBorder}`,
                                background: disabled || !canSubmit
                                    ? (isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)')
                                    : selectedTint,
                                color: disabled || !canSubmit
                                    ? 'var(--app-foreground-muted)'
                                    : 'var(--app-primary)',
                                fontSize: 13,
                                fontWeight: 600,
                                cursor: disabled || !canSubmit ? 'default' : 'pointer',
                                boxShadow: disabled || !canSubmit
                                    ? 'none'
                                    : (isDark ? 'var(--app-shadow-control)' : 'var(--app-shadow-control)'),
                            }}
                        >
                            {schema.submit_label || t('home.interaction.continue', 'Submit')}
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    const isAnswered = !!selectedValue
    const question = String(interaction.question || '').trim()
    const requestId = String(interaction.request_id || '').trim()
    const primaryField = getPrimaryField(interaction)
    const options = Array.isArray(primaryField?.options) ? primaryField.options : []
    const displayMode = resolveDisplayMode(primaryField, options)

    if (!question || !requestId || options.length === 0) {
        return null
    }

    return (
        <div data-testid="interaction-card-shell" style={shellStyle}>
            <div style={{
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
            }}>
                <MessageSquareMore size={16} color="var(--app-primary)" style={{ marginTop: 2, flexShrink: 0 }} />
                <div style={{
                    fontSize: 14,
                    color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                    lineHeight: 1.5,
                }}>
                    <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                            p: ({ children }) => <p style={{ margin: '2px 0' }}>{children}</p>,
                            strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
                            ul: ({ children }) => <ul style={{ margin: '4px 0', paddingLeft: 18 }}>{children}</ul>,
                            ol: ({ children }) => <ol style={{ margin: '4px 0', paddingLeft: 18 }}>{children}</ol>,
                            li: ({ children }) => <li style={{ margin: '2px 0' }}>{children}</li>,
                            code: ({ children }) => (
                                <code style={{
                                    padding: '1px 4px',
                                    borderRadius: 6,
                                    backgroundColor: isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)',
                                    fontSize: 13,
                                }}>{children}</code>
                            ),
                            table: ({ children }) => (
                                <div style={{ overflowX: 'auto', margin: '6px 0' }}>
                                    <table style={{
                                        width: '100%',
                                        borderCollapse: 'collapse',
                                        borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)',
                                        fontSize: 13,
                                    }}>{children}</table>
                                </div>
                            ),
                            th: ({ children }) => (
                                <th style={{
                                    padding: '6px 8px',
                                    borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)',
                                    backgroundColor: isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)',
                                    textAlign: 'left',
                                    fontWeight: 600,
                                }}>{children}</th>
                            ),
                            td: ({ children }) => (
                                <td style={{
                                    padding: '6px 8px',
                                    borderWidth: 1, borderStyle: 'solid', borderColor: 'var(--app-border)',
                                }}>{children}</td>
                            ),
                        }}
                    >
                        {question}
                    </ReactMarkdown>
                </div>
            </div>

            <div style={{ padding: '0 16px 12px' }}>
                {summaryLabel ? (
                    <div style={{
                        marginBottom: 10,
                        display: 'inline-flex',
                        maxWidth: '100%',
                        alignItems: 'center',
                        gap: 6,
                        padding: '7px 10px',
                        borderRadius: 999,
                        border: `1px solid ${accentBorder}`,
                        background: selectedTint,
                        color: 'var(--app-primary)',
                        fontSize: 12,
                        fontWeight: 600,
                        boxShadow: isDark ? 'var(--app-shadow-control)' : 'var(--app-shadow-control)',
                    }}>
                        <Check size={12} />
                        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {summaryLabel}
                        </span>
                    </div>
                ) : null}
                {(displayMode === 'buttons' || displayMode === 'text_input') && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            {options.map((opt: InteractionOption) => (
                                <button
                                    key={opt.value}
                                    onClick={() => handleSelect(opt.value, opt.label)}
                                    disabled={isAnswered || disabled}
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: 999,
                                        border: selectedValue === opt.value
                                            ? `1px solid ${accentBorder}`
                                            : `1px solid ${mutedBorder}`,
                                        background: selectedValue === opt.value ? selectedTint : 'transparent',
                                        color: selectedValue === opt.value
                                            ? 'var(--app-primary)'
                                            : (isDark ? 'var(--app-foreground)' : 'var(--app-foreground-muted)'),
                                        fontSize: 13,
                                        cursor: isAnswered || disabled ? 'default' : 'pointer',
                                        opacity: isAnswered && selectedValue !== opt.value ? 0.45 : 1,
                                        transition: 'all 0.2s ease',
                                        boxShadow: selectedValue === opt.value
                                            ? (isDark ? 'var(--app-shadow-control)' : 'var(--app-shadow-control)')
                                            : 'none',
                                    }}
                                >
                                    {opt.label}
                                </button>
                            ))}

                            {!isAnswered && !showOtherInput && (
                                <button
                                    onClick={handleOtherClick}
                                    disabled={disabled}
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: 999,
                                        border: '1px dashed var(--app-border-strong)',
                                        backgroundColor: 'transparent',
                                        color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                                        fontSize: 13,
                                        cursor: disabled ? 'default' : 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 4,
                                        transition: 'all 0.2s ease',
                                    }}
                                >
                                    <Edit3 size={12} />
                                    {t('canvas.chat.interaction.other')}
                                </button>
                            )}
                        </div>

                        {showOtherInput && !isAnswered && (
                            <div style={{
                                display: 'flex',
                                gap: 8,
                                alignItems: 'center',
                                animation: 'slideUp 0.2s ease-out',
                            }}>
                                <input
                                    value={otherText}
                                    onChange={(e) => setOtherText(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleOtherSubmit()}
                                    autoFocus
                                    placeholder={t('canvas.chat.interaction.other_placeholder')}
                                    style={{
                                        flex: 1,
                                        ...fieldSurfaceStyle,
                                        borderRadius: 999,
                                    }}
                                />
                                <button
                                    onClick={handleOtherSubmit}
                                    disabled={!otherText.trim() || disabled}
                                    style={{
                                        width: 32,
                                        height: 32,
                                        borderRadius: '50%',
                                        border: 'none',
                                        backgroundColor: otherText.trim() ? 'var(--app-primary)' : (isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)'),
                                        color: otherText.trim() ? 'var(--app-primary-foreground)' : 'var(--app-foreground-muted)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        cursor: otherText.trim() && !disabled ? 'pointer' : 'default',
                                        transition: 'all 0.2s ease',
                                    }}
                                >
                                    <Send size={14} />
                                </button>
                            </div>
                        )}
                    </div>
                )}

                {displayMode === 'cards' && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 10 }}>
                        {options.map((opt: InteractionOption) => (
                            <div
                                key={opt.value}
                                onClick={() => !isAnswered && !disabled && handleSelect(opt.value, opt.label)}
                                style={{
                                    borderRadius: 16,
                                    border: selectedValue === opt.value
                                        ? `1px solid ${accentBorder}`
                                        : `1px solid ${mutedBorder}`,
                                    background: subtleSurface,
                                    overflow: 'hidden',
                                    cursor: isAnswered || disabled ? 'default' : 'pointer',
                                    opacity: isAnswered && selectedValue !== opt.value ? 0.45 : 1,
                                    transition: 'all 0.2s ease',
                                    boxShadow: selectedValue === opt.value
                                        ? (isDark ? 'var(--app-shadow-control)' : 'var(--app-shadow-control)')
                                        : 'none',
                                }}
                            >
                                {opt.preview_url && (
                                    <img
                                        src={opt.preview_url}
                                        alt={opt.label}
                                        style={{ width: '100%', height: 80, objectFit: 'cover' }}
                                    />
                                )}
                                <div style={{ padding: '8px 10px' }}>
                                    <div style={{ fontSize: 13, fontWeight: 500, color: (isDark && selectedValue === opt.value) ? 'var(--app-primary)' : (isDark ? 'var(--app-foreground)' : (selectedValue === opt.value ? 'var(--app-primary)' : 'var(--app-foreground)')) }}>
                                        {opt.label}
                                    </div>
                                    {opt.description && (
                                        <div style={{ fontSize: 11, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)', marginTop: 2 }}>
                                            {opt.description}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {displayMode === 'color_picker' && (
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                        {options.map((opt: InteractionOption) => (
                            <div
                                key={opt.value}
                                onClick={() => !isAnswered && !disabled && handleSelect(opt.value, opt.label)}
                                style={{
                                    width: 40,
                                    height: 40,
                                    borderRadius: 12,
                                    backgroundColor: opt.value,
                                    border: selectedValue === opt.value
                                        ? '3px solid var(--app-primary)'
                                        : '2px solid var(--app-border)',
                                    cursor: isAnswered || disabled ? 'default' : 'pointer',
                                    boxShadow: 'var(--app-shadow-control)',
                                    opacity: isAnswered && selectedValue !== opt.value ? 0.4 : 1,
                                    transition: 'all 0.2s ease',
                                }}
                                title={opt.label}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
