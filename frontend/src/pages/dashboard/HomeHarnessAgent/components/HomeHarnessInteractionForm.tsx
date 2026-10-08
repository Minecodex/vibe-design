import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Eye, Loader2 } from 'lucide-react'
import type { TFunction } from 'i18next'

import type { HarnessDesignSystemRead, InteractionField, InteractionOption, InteractionQuestion } from '@/api/endpoints/agent'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { localizeInteractionSchema } from './homeInteractionI18n'
import { buildInteractionDisplayLabel } from './homeInteractionSummary'
import { HomeDesignSystemPreviewDialog } from './HomeDesignSystemPreviewDialog'
import { HomeChatMarkdown } from './HomeChatMarkdown'

type HomeInteractionOption = InteractionOption & {
  previewUrl?: string | null
  optionType?: string | null
  isCustomOther?: boolean | null
}

type HomeInteractionField = InteractionField & {
  defaultValue?: any
  maxSelections?: number | null
  options?: HomeInteractionOption[]
}

type HomeInteractionQuestion = InteractionQuestion & {
  maxSelections?: number | null
  options?: HomeInteractionOption[]
}

const OTHER_SELECTION_VALUE = '__ask_user_other__'

function isQuestionRequired(question: HomeInteractionQuestion): boolean {
  return question.required !== false
}

function hasSyntheticOtherOption(field: HomeInteractionField): boolean {
  return (field.options || []).some((option) => {
    const optionRecord = option as InteractionOption & { isCustomOther?: boolean | null }
    return (
      String(option.value || '').trim() === OTHER_SELECTION_VALUE
      || Boolean(optionRecord.is_custom_other ?? optionRecord.isCustomOther)
    )
  })
}

function usesStructuredSelectionAnswers(kind: string | undefined): boolean {
  return kind === 'ask_user' || kind === 'quick_brief'
}

function supportsCustomOther(kind: string | undefined, field: HomeInteractionField): boolean {
  return usesStructuredSelectionAnswers(kind)
    && ['radio', 'cards', 'checkbox'].includes(String(field.type || '').trim())
    && !hasSyntheticOtherOption(field)
}

interface HomeHarnessInteractionFormProps {
  requestId: string
  kind?: string
  question?: string
  content?: string | null
  fallbackContent?: string | null
  language?: string
  phase?: string | null
  schema?: {
    title: string
    description?: string | null
    submit_label?: string | null
    submitLabel?: string | null
    fields?: HomeInteractionField[]
    questions?: HomeInteractionQuestion[]
  } | null
  answers?: Record<string, any> | null
  status?: 'pending' | 'submitted'
  submittedLabel?: string
  isDark: boolean
  isSubmitting?: boolean
  t: TFunction
  onSubmit?: (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
  ) => Promise<void>
}

function defaultAnswersFromSchema(schema?: HomeHarnessInteractionFormProps['schema']): Record<string, any> {
  const defaults: Record<string, any> = {}
  for (const field of schema?.fields || []) {
    const defaultValue = field.default_value !== undefined ? field.default_value : field.defaultValue
    if (defaultValue !== undefined) {
      defaults[field.id] = defaultValue
      continue
    }
    defaults[field.id] = field.type === 'checkbox' ? [] : ''
  }
  for (const question of schema?.questions || []) {
    const defaultValue = (question as Record<string, any>).default_value ?? (question as Record<string, any>).defaultValue
    if (defaultValue !== undefined) {
      defaults[question.id] = defaultValue
      continue
    }
    defaults[question.id] = question.type === 'multiple' ? [] : ''
  }
  return defaults
}

function buildInitialInteractionState(
  schema?: HomeHarnessInteractionFormProps['schema'],
  answers?: Record<string, any> | null,
): { formAnswers: Record<string, any>, otherAnswers: Record<string, string> } {
  const formAnswers = { ...defaultAnswersFromSchema(schema) }
  const otherAnswers: Record<string, string> = {}

  for (const field of schema?.fields || []) {
    const answer = answers?.[field.id]
    if (answer === undefined) {
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
      formAnswers[field.id] = answer.map((entry) => {
        if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
          const source = entry as Record<string, any>
          if (String(source.type || '').trim() === 'other') {
            otherAnswers[field.id] = String(source.value || '').trim()
            return OTHER_SELECTION_VALUE
          }
          return String(source.value || '').trim()
        }
        return String(entry || '').trim()
      }).filter(Boolean)
      continue
    }

    formAnswers[field.id] = typeof answer === 'string'
      ? answer
      : (answer && typeof answer === 'object' && !Array.isArray(answer))
        ? String((answer as Record<string, any>).value || '').trim()
        : answer
  }

  for (const question of schema?.questions || []) {
    const answer = answers?.[question.id]
    if (answer === undefined) {
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
      formAnswers[question.id] = answer.map((entry) => {
        if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
          const source = entry as Record<string, any>
          if (String(source.type || '').trim() === 'other') {
            otherAnswers[question.id] = String(source.value || '').trim()
            return OTHER_SELECTION_VALUE
          }
          return String(source.value || '').trim()
        }
        return String(entry || '').trim()
      }).filter(Boolean)
      continue
    }

    formAnswers[question.id] = answer
  }

  return { formAnswers, otherAnswers }
}

function textareaClassName(): string {
  return cn(
    'flex min-h-24 w-full min-w-0 rounded-xl border px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none',
    'placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
    'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
    'border-[var(--app-border)] bg-[var(--app-control)] text-foreground',
  )
}

function selectTriggerClassName(): string {
  return cn(
    'h-10 w-full justify-between rounded-xl shadow-xs',
    'border-[var(--app-border)] bg-[var(--app-control)] text-foreground hover:bg-[var(--app-control-hover)]',
  )
}

function selectContentClassName(): string {
  return cn(
    'rounded-xl border shadow-md',
    'border-[var(--app-border)] bg-[var(--app-glass)] text-foreground backdrop-blur-2xl',
  )
}

function selectItemClassName(): string {
  return cn(
    'rounded-lg px-3 py-2 text-sm focus:text-current',
    'focus:bg-[var(--app-control-hover)] data-[state=checked]:bg-[var(--app-control-selected)] data-[state=checked]:text-[var(--app-control-selected-foreground)]',
  )
}

function surfaceButtonClassName(selected = false): string {
  if (selected) {
    return cn(
      'border shadow-xs',
      'border-[var(--app-border-strong)] bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)]',
    )
  }

  return cn(
    'border shadow-xs transition-colors',
    'border-[var(--app-border)] bg-[var(--app-control)] text-foreground hover:bg-[var(--app-control-hover)]',
  )
}

function previewButtonClassName(): string {
  return cn(
    'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-xs transition-colors',
    'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
  )
}

function submitButtonClassName(): string {
  return cn(
    'h-10 rounded-xl border px-4 shadow-xs transition-colors',
    'border-[var(--app-border)] bg-[var(--app-control)] text-foreground hover:bg-[var(--app-control-hover)]',
  )
}

function renderSelectedIndicator(selected: boolean) {
  return selected ? <Check className="h-4 w-4 shrink-0" aria-hidden="true" /> : null
}

function buildPreviewDesignSystem(option: HomeInteractionOption, kind?: string | null): HarnessDesignSystemRead | null {
  const rawValue = String(option.value || '').trim()
  if (!rawValue) {
    return null
  }
  const id = kind === 'design_system_picker' ? rawValue : ''
  if (!id) {
    return null
  }
  return {
    id,
    title: String(option.label || id).trim(),
    description: String(option.description || option.metadata?.category || '').trim(),
    category: option.metadata?.category ? String(option.metadata.category).trim() : null,
    sections: [],
    palette: Array.isArray(option.metadata?.palette) ? option.metadata.palette as string[] : [],
    preview: null,
    featured: null,
    is_default: false,
  }
}

export function HomeHarnessInteractionForm({
  requestId,
  kind,
  question,
  language,
  phase,
  schema,
  answers,
  content,
  fallbackContent,
  status = 'pending',
  submittedLabel,
  isDark,
  isSubmitting = false,
  t,
  onSubmit,
}: HomeHarnessInteractionFormProps) {
  const localizedSchema = useMemo(
    () => localizeInteractionSchema(kind, schema, language) as HomeHarnessInteractionFormProps['schema'],
    [kind, language, schema],
  )
  const initialState = useMemo(
    () => buildInitialInteractionState(localizedSchema, answers),
    [answers, localizedSchema],
  )
  const [formAnswers, setFormAnswers] = useState<Record<string, any>>(() => initialState.formAnswers)
  const [otherAnswers, setOtherAnswers] = useState<Record<string, string>>(() => initialState.otherAnswers)
  const initialStateKey = useMemo(() => JSON.stringify(initialState), [initialState])
  const lastSyncedStateKeyRef = useRef(`${requestId}:${initialStateKey}`)
  const [previewDesignSystem, setPreviewDesignSystem] = useState<HarnessDesignSystemRead | null>(null)

  useEffect(() => {
    const syncKey = `${requestId}:${initialStateKey}`
    if (lastSyncedStateKeyRef.current === syncKey) {
      return
    }
    lastSyncedStateKeyRef.current = syncKey
    setFormAnswers(initialState.formAnswers)
    setOtherAnswers(initialState.otherAnswers)
  }, [initialState, initialStateKey, requestId])

  const isSubmitted = status === 'submitted'
  const normalizedPhase = String(phase || '').trim().toLowerCase()
  const askUserQuestions = localizedSchema?.questions || []
  const hasAskUserQuestions = kind === 'ask_user' && askUserQuestions.length > 0
  const hasLegacyAskUserFields = kind === 'ask_user' && !hasAskUserQuestions && (localizedSchema?.fields || []).length > 0
  const canFinishPlanInterview = hasAskUserQuestions && (normalizedPhase === 'planning' || normalizedPhase === 'revising_plan')

  const canSubmitAskUser = askUserQuestions.every((question) => {
    const value = formAnswers[question.id]
    if (question.type === 'input') {
      return !isQuestionRequired(question) || String(value ?? '').trim().length > 0
    }
    if (question.type === 'multiple') {
      const selectedValues = Array.isArray(value) ? value : []
      if (selectedValues.length === 0) {
        return false
      }
      if (selectedValues.includes(OTHER_SELECTION_VALUE)) {
        return String(otherAnswers[question.id] ?? '').trim().length > 0
      }
      return true
    }
    if (value === OTHER_SELECTION_VALUE) {
      return String(otherAnswers[question.id] ?? '').trim().length > 0
    }
    return String(value ?? '').trim().length > 0
  })

  const canSubmitFields = (localizedSchema?.fields || []).every((field) => {
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
        return String(otherAnswers[field.id] ?? '').trim().length > 0
      }
      return true
    }
    if (supportsCustomOther(kind, field) && value === OTHER_SELECTION_VALUE) {
      return String(otherAnswers[field.id] ?? '').trim().length > 0
    }
    return String(value ?? '').trim().length > 0
  })
  const canSubmit = hasAskUserQuestions ? canSubmitAskUser : canSubmitFields

  const buildSubmitAnswers = (
    answerSource: Record<string, any> = formAnswers,
    otherSource: Record<string, string> = otherAnswers,
  ): Record<string, any> => {
    if (kind === 'ask_user') {
      const nextAnswers: Record<string, any> = {}
      for (const question of askUserQuestions) {
        const value = answerSource[question.id]
        if (question.type === 'input') {
          const normalized = String(value ?? '').trim()
          nextAnswers[question.id] = {
            type: 'input',
            value: normalized,
            label: normalized,
          }
          continue
        }
        if (question.type === 'multiple') {
          const selectedValues = Array.isArray(value) ? value : []
          nextAnswers[question.id] = selectedValues
            .map((entry) => {
              if (entry === OTHER_SELECTION_VALUE) {
                const otherValue = String(otherSource[question.id] ?? '').trim()
                const otherLabel = String(t('home.interaction.otherOption', 'Other')).trim()
                return {
                  type: 'other',
                  value: otherValue,
                  label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
                }
              }
              const normalized = String(entry ?? '').trim()
              const option = (question.options || []).find((candidate) => candidate.value === normalized)
              return normalized
                ? {
                    type: 'option',
                    value: normalized,
                    label: option?.label || normalized,
                  }
                : null
            })
            .filter(Boolean)
          continue
        }
        if (value === OTHER_SELECTION_VALUE) {
          const otherValue = String(otherSource[question.id] ?? '').trim()
          const otherLabel = String(t('home.interaction.otherOption', 'Other')).trim()
          nextAnswers[question.id] = {
            type: 'other',
            value: otherValue,
            label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
          }
          continue
        }
        const normalized = String(value ?? '').trim()
        const option = (question.options || []).find((candidate) => candidate.value === normalized)
        nextAnswers[question.id] = {
          type: 'option',
          value: normalized,
          label: option?.label || normalized,
        }
      }
      return nextAnswers
    }

    if (!usesStructuredSelectionAnswers(kind)) {
      return formAnswers
    }
    const nextAnswers: Record<string, any> = {}
    for (const field of localizedSchema?.fields || []) {
      const value = answerSource[field.id]
      if (field.type === 'checkbox') {
        const selectedValues = Array.isArray(value) ? value : []
        nextAnswers[field.id] = selectedValues
          .map((entry) => {
            if (entry === OTHER_SELECTION_VALUE) {
              const otherValue = String(otherSource[field.id] ?? '').trim()
              const otherLabel = String(field.other_label || t('home.interaction.otherOption', 'Other')).trim()
              return {
                type: 'other',
                value: otherValue,
                label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
              }
            }
            const normalized = String(entry ?? '').trim()
            return normalized || null
          })
          .filter(Boolean)
        continue
      }
      if (field.type !== 'radio' && field.type !== 'cards') {
        nextAnswers[field.id] = value
        continue
      }
      if (value === OTHER_SELECTION_VALUE) {
        const otherValue = String(otherSource[field.id] ?? '').trim()
        const otherLabel = String(field.other_label || t('home.interaction.otherOption', 'Other')).trim()
        nextAnswers[field.id] = {
          type: 'other',
          value: otherValue,
          label: otherValue ? `${otherLabel}: ${otherValue}` : otherLabel,
        }
        continue
      }
      const option = (field.options || []).find((candidate) => candidate.value === value)
      nextAnswers[field.id] = {
        type: 'option',
        value: String(value ?? '').trim(),
        label: option?.label || String(value ?? '').trim(),
      }
    }
    return nextAnswers
  }

  const handleSubmit = async () => {
    if (!localizedSchema || !onSubmit || isSubmitting || isSubmitted || !canSubmit) {
      return
    }
    const submitAnswers = buildSubmitAnswers()
    const displayLabel = buildInteractionDisplayLabel(kind, localizedSchema, submitAnswers, language)
    await onSubmit(requestId, JSON.stringify(submitAnswers), displayLabel, undefined, submitAnswers)
  }

  const handleSingleQuestionOptionClick = async (askQuestion: HomeInteractionQuestion, value: string) => {
    const nextFormAnswers = { ...formAnswers, [askQuestion.id]: value }
    setFormAnswers(nextFormAnswers)
    if (
      askQuestion.type !== 'single'
      || askUserQuestions.length !== 1
      || !localizedSchema
      || !onSubmit
      || isSubmitting
      || isSubmitted
    ) {
      return
    }
    const submitAnswers = buildSubmitAnswers(nextFormAnswers, otherAnswers)
    const displayLabel = buildInteractionDisplayLabel(kind, localizedSchema, submitAnswers, language)
    await onSubmit(requestId, JSON.stringify(submitAnswers), displayLabel, undefined, submitAnswers)
  }

  const handleFinishPlanInterview = async () => {
    if (!localizedSchema || !onSubmit || isSubmitting || isSubmitted) {
      return
    }
    const submitAnswers = buildSubmitAnswers()
    const displayLabel = t('home.interaction.finishPlanInterviewLabel', 'Information is enough. Continue planning.')
    const answer = [
      'The user has indicated they have provided enough answers for the plan interview.',
      'Stop asking clarifying questions and proceed to finish the plan with the information you have.',
      `Questions and answers: ${JSON.stringify(submitAnswers)}`,
    ].join('\n')
    await onSubmit(requestId, answer, displayLabel, false, {
      ...submitAnswers,
      __finish_plan_interview: true,
    })
  }

  if (!localizedSchema) {
    return null
  }

  const markdownContent = typeof content === 'string' ? content.trim() : ''
  const fallbackQuestionContent = !markdownContent && typeof question === 'string' && question.trim() !== localizedSchema.title
    ? question.trim()
    : ''
  const fallbackMessageContent = !markdownContent
    && !fallbackQuestionContent
    && typeof fallbackContent === 'string'
    && fallbackContent.trim() !== localizedSchema.title
      ? fallbackContent.trim()
      : ''
  const displayMarkdownContent = markdownContent || fallbackQuestionContent || fallbackMessageContent
  const shouldRenderHeading = displayMarkdownContent.length === 0
  const description = shouldRenderHeading ? localizedSchema.description : null

  if (hasLegacyAskUserFields) {
    return (
      <div
        className={cn(
          'max-w-[90%] rounded-2xl border px-4 py-4',
          'border-[var(--app-border)] bg-[var(--app-surface-muted)]',
        )}
      >
        <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
          {localizedSchema.title}
        </div>
        <p className={cn('mt-2 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
          {t('home.interaction.legacyAskUserUnsupported', 'This question was created by an older interaction format and cannot be continued. Please start a new request.')}
        </p>
      </div>
    )
  }

  if (hasAskUserQuestions) {
    return (
      <div
        className={cn(
          'max-w-[90%] rounded-2xl border px-4 py-4',
          'border-[var(--app-border)] bg-[var(--app-surface-muted)]',
        )}
      >
        {displayMarkdownContent ? (
          <HomeChatMarkdown
            content={displayMarkdownContent}
            isDark={isDark}
            className="mb-4 text-sm"
          />
        ) : null}
        {shouldRenderHeading ? (
          <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
            {localizedSchema.title}
          </div>
        ) : null}
        {description ? (
          <p className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
            {description}
          </p>
        ) : null}
        <div className="mt-4 space-y-5">
          {askUserQuestions.map((askQuestion) => {
            const selectedValue = formAnswers[askQuestion.id]
            const selectedValues = Array.isArray(selectedValue) ? selectedValue as string[] : []
            const maxSelections = askQuestion.max_selections ?? askQuestion.maxSelections ?? null
            const maxReached = askQuestion.type === 'multiple'
              && typeof maxSelections === 'number'
              && selectedValues.length >= maxSelections
            return (
              <div key={askQuestion.id} className="space-y-2">
                <div className="space-y-1">
                  <div className={cn('text-xs font-semibold uppercase tracking-normal', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                    {askQuestion.header}
                  </div>
                  <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-800')}>
                    {askQuestion.question}
                  </div>
                </div>
                <div className={cn(askQuestion.type === 'multiple' ? 'flex flex-wrap gap-2' : 'flex flex-wrap gap-2')}>
                  {askQuestion.type === 'input' ? (
                    <Input
                      id={`${requestId}-${askQuestion.id}`}
                      aria-label={askQuestion.question}
                      value={String(selectedValue ?? '')}
                      disabled={isSubmitted || isSubmitting}
                      placeholder={t('home.interaction.askUserPlaceholder', 'Type your response...')}
                      onChange={(event) => setFormAnswers((current) => ({ ...current, [askQuestion.id]: event.target.value }))}
                      className="h-10 rounded-xl"
                    />
                  ) : null}
                  {askQuestion.type !== 'input' ? (askQuestion.options || []).map((option) => {
                    const selected = askQuestion.type === 'multiple'
                      ? selectedValues.includes(option.value)
                      : String(selectedValue ?? '') === option.value
                    const disabled = isSubmitted || isSubmitting || (askQuestion.type === 'multiple' && maxReached && !selected)
                    return (
                      <button
                        key={`${askQuestion.id}-${option.value}`}
                        type="button"
                        disabled={disabled}
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
                          void handleSingleQuestionOptionClick(askQuestion, option.value)
                        }}
                        className={cn(
                          askQuestion.type === 'multiple' ? 'rounded-full px-3 py-2 text-sm' : 'rounded-xl px-3 py-2 text-left text-sm',
                          surfaceButtonClassName(selected),
                          disabled ? 'opacity-60' : '',
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="font-medium">{option.label}</div>
                          {renderSelectedIndicator(selected)}
                        </div>
                        {option.description ? (
                          <div className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                            {option.description}
                          </div>
                        ) : null}
                      </button>
                    )
                  }) : null}
                  {askQuestion.type !== 'input' ? (
                    <button
                    type="button"
                    disabled={isSubmitted || isSubmitting || (askQuestion.type === 'multiple' && maxReached && !selectedValues.includes(OTHER_SELECTION_VALUE))}
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
                    className={cn(
                      askQuestion.type === 'multiple' ? 'rounded-full px-3 py-2 text-sm' : 'rounded-xl px-3 py-2 text-left text-sm',
                      surfaceButtonClassName(
                        askQuestion.type === 'multiple'
                          ? selectedValues.includes(OTHER_SELECTION_VALUE)
                          : selectedValue === OTHER_SELECTION_VALUE,
                      ),
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span>{t('home.interaction.otherOption', 'Other')}</span>
                      {renderSelectedIndicator(
                        askQuestion.type === 'multiple'
                          ? selectedValues.includes(OTHER_SELECTION_VALUE)
                          : selectedValue === OTHER_SELECTION_VALUE,
                      )}
                    </div>
                    </button>
                  ) : null}
                </div>
                {(
                  askQuestion.type === 'multiple'
                    ? selectedValues.includes(OTHER_SELECTION_VALUE)
                    : selectedValue === OTHER_SELECTION_VALUE
                ) ? (
                  <Input
                    id={`${requestId}-${askQuestion.id}`}
                    aria-label={askQuestion.question}
                    value={otherAnswers[askQuestion.id] || ''}
                    disabled={isSubmitted || isSubmitting}
                    placeholder={t('home.interaction.askUserPlaceholder', 'Type your response...')}
                    onChange={(event) => setOtherAnswers((current) => ({ ...current, [askQuestion.id]: event.target.value }))}
                    className="h-10 rounded-xl"
                  />
                ) : null}
              </div>
            )
          })}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className={cn('min-w-0 flex-1 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
            {isSubmitted ? (submittedLabel || t('home.interaction.submitted', 'Submitted')) : ''}
          </div>
          {!isSubmitted ? (
            <div className="flex flex-wrap items-center gap-2">
              {canFinishPlanInterview ? (
                <Button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => void handleFinishPlanInterview()}
                  variant="ghost"
                  className="h-10 rounded-xl px-3"
                >
                  {t('home.interaction.finishPlanInterview', 'Enough info, continue')}
                </Button>
              ) : null}
              <Button
                type="button"
                disabled={!canSubmit || isSubmitting}
                onClick={() => void handleSubmit()}
                variant="outline"
                className={submitButtonClassName()}
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {localizedSchema.submit_label || localizedSchema.submitLabel || t('home.interaction.continue', 'Continue')}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'max-w-[90%] rounded-2xl border px-4 py-4',
        'border-[var(--app-border)] bg-[var(--app-surface-muted)]',
      )}
    >
      {displayMarkdownContent ? (
        <HomeChatMarkdown
          content={displayMarkdownContent}
          isDark={isDark}
          className="mb-4 text-sm"
        />
      ) : null}
      {shouldRenderHeading ? (
        <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
          {localizedSchema.title}
        </div>
      ) : null}
      {description ? (
        <p className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
          {description}
        </p>
      ) : null}
      <div className="mt-4 space-y-4">
        {(localizedSchema.fields || []).map((field) => (
          <div key={field.id} className="space-y-2">
            <label
              htmlFor={`${requestId}-${field.id}`}
              className={cn('block text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-800')}
            >
              {field.label}
              {field.required ? <span className="ml-1 text-red-500">*</span> : null}
            </label>
            {field.type === 'text' ? (
              <Input
                id={`${requestId}-${field.id}`}
                aria-label={field.label}
                value={String(formAnswers[field.id] ?? '')}
                disabled={isSubmitted || isSubmitting}
                placeholder={field.placeholder || ''}
                onChange={(event) => setFormAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                className="h-10 rounded-xl"
              />
            ) : null}
            {field.type === 'textarea' ? (
              <textarea
                id={`${requestId}-${field.id}`}
                aria-label={field.label}
                value={String(formAnswers[field.id] ?? '')}
                disabled={isSubmitted || isSubmitting}
                placeholder={field.placeholder || ''}
                rows={4}
                onChange={(event) => setFormAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                className={textareaClassName()}
              />
            ) : null}
            {field.type === 'select' ? (
              <Select
                value={String(formAnswers[field.id] ?? '')}
                onValueChange={(value) => setFormAnswers((current) => ({ ...current, [field.id]: value }))}
                disabled={isSubmitted || isSubmitting}
              >
                <SelectTrigger
                  id={`${requestId}-${field.id}`}
                  aria-label={field.label}
                  className={selectTriggerClassName()}
                >
                  <SelectValue placeholder={field.placeholder || t('home.interaction.selectPlaceholder', 'Select')} />
                </SelectTrigger>
                <SelectContent className={selectContentClassName()}>
                  <SelectItem value="__placeholder__" disabled className="hidden">
                    {field.placeholder || t('home.interaction.selectPlaceholder', 'Select')}
                  </SelectItem>
                  {(field.options || []).map((option) => (
                    <SelectItem key={`${field.id}-${option.value}`} value={option.value} className={selectItemClassName()}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            {(field.type === 'radio' || field.type === 'cards') ? (
              <div className={cn(field.type === 'cards' ? 'grid gap-3 md:grid-cols-2' : 'flex flex-wrap gap-2')}>
                {(field.options || []).map((option) => {
                  const selected = String(formAnswers[field.id] ?? '') === option.value
                  const palette = Array.isArray(option.metadata?.palette) ? option.metadata.palette as string[] : []
                  const displayFont = option.metadata?.display_font ?? option.metadata?.displayFont
                  const bodyFont = option.metadata?.body_font ?? option.metadata?.bodyFont
                  const references = Array.isArray(option.metadata?.references)
                    ? (option.metadata.references as string[]).map((reference) => String(reference).trim()).filter(Boolean)
                    : []
                  const previewDesignSystemOption = field.type === 'cards' ? buildPreviewDesignSystem(option, kind) : null
                  if (field.type === 'cards') {
                    return (
                      <div
                        key={`${field.id}-${option.value}`}
                        role="button"
                        tabIndex={isSubmitted || isSubmitting ? -1 : 0}
                        aria-pressed={selected}
                        onClick={() => {
                          if (isSubmitted || isSubmitting) {
                            return
                          }
                          setFormAnswers((current) => ({ ...current, [field.id]: option.value }))
                        }}
                        onKeyDown={(event) => {
                          if (isSubmitted || isSubmitting) {
                            return
                          }
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setFormAnswers((current) => ({ ...current, [field.id]: option.value }))
                          }
                        }}
                        className={cn(
                          'rounded-xl p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/40',
                          surfaceButtonClassName(selected),
                          (isSubmitted || isSubmitting) ? 'cursor-not-allowed opacity-70' : 'cursor-pointer',
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-base font-semibold">{option.label}</div>
                          {renderSelectedIndicator(selected)}
                        </div>
                        {option.description ? (
                          <div className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                            {option.description}
                          </div>
                        ) : null}
                        <div className="mt-3 space-y-3">
                          {palette.length > 0 ? (
                            <div className="flex gap-2">
                              {palette.map((color) => (
                                <span key={`${option.value}-${color}`} className="h-6 w-6 rounded-full border border-[var(--app-border)]" style={{ backgroundColor: color }} />
                              ))}
                            </div>
                          ) : null}
                          <div className={cn('space-y-1 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
                            {option.metadata?.mood ? <div>{t('home.interaction.directionMeta.mood', 'Mood')}: {String(option.metadata.mood)}</div> : null}
                            {displayFont ? <div>{t('home.interaction.directionMeta.displayFont', 'Display')}: {String(displayFont)}</div> : null}
                            {bodyFont ? <div>{t('home.interaction.directionMeta.bodyFont', 'Body')}: {String(bodyFont)}</div> : null}
                            {(references.length > 0 || previewDesignSystemOption) ? (
                              <div
                                data-testid="design-system-card-meta-row"
                                className="flex items-center justify-between gap-3"
                              >
                                {references.length > 0 ? (
                                  <div className="min-w-0 flex-1 truncate">
                                    {t('home.interaction.directionMeta.references', 'Refs')}: {references.join(' / ')}
                                  </div>
                                ) : (
                                  <div />
                                )}
                                {previewDesignSystemOption ? (
                                  <button
                                    type="button"
                                    disabled={isSubmitted || isSubmitting}
                                    onClick={(event) => {
                                      event.preventDefault()
                                      event.stopPropagation()
                                      setPreviewDesignSystem(previewDesignSystemOption)
                                    }}
                                    className={cn(previewButtonClassName(), 'shrink-0')}
                                  >
                                    <Eye className="h-3 w-3" />
                                    <span>{t('home.designSystem.showcaseTab', '示例')}</span>
                                  </button>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    )
                  }
                  return (
                    <button
                      key={`${field.id}-${option.value}`}
                      type="button"
                      disabled={isSubmitted || isSubmitting}
                      onClick={() => setFormAnswers((current) => ({ ...current, [field.id]: option.value }))}
                      className={cn(
                        'rounded-xl px-3 py-2 text-left text-sm',
                        surfaceButtonClassName(selected),
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium">{option.label}</div>
                        {renderSelectedIndicator(selected)}
                      </div>
                      {option.description ? (
                        <div className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                          {option.description}
                        </div>
                      ) : null}
                    </button>
                  )
                })}
                {supportsCustomOther(kind, field) ? (
                  <button
                    type="button"
                    disabled={isSubmitted || isSubmitting}
                    onClick={() => setFormAnswers((current) => ({ ...current, [field.id]: OTHER_SELECTION_VALUE }))}
                    className={cn(
                      'rounded-xl px-3 py-2 text-left text-sm',
                      surfaceButtonClassName(formAnswers[field.id] === OTHER_SELECTION_VALUE),
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium">
                        {field.other_label || t('home.interaction.otherOption', 'Other')}
                      </div>
                      {renderSelectedIndicator(formAnswers[field.id] === OTHER_SELECTION_VALUE)}
                    </div>
                  </button>
                ) : null}
              </div>
            ) : null}
            {(field.type === 'radio' || field.type === 'cards') && supportsCustomOther(kind, field) && formAnswers[field.id] === OTHER_SELECTION_VALUE ? (
              <Input
                id={`${requestId}-${field.id}`}
                aria-label={field.label}
                value={otherAnswers[field.id] || ''}
                disabled={isSubmitted || isSubmitting}
                placeholder={field.other_placeholder || field.placeholder || t('home.interaction.askUserPlaceholder', 'Type your response...')}
                onChange={(event) => setOtherAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                className="h-10 rounded-xl"
              />
            ) : null}
            {field.type === 'checkbox' ? (
              <div className="flex flex-wrap gap-2">
                {(field.options || []).map((option) => {
                  const currentValues = Array.isArray(formAnswers[field.id]) ? formAnswers[field.id] as string[] : []
                  const selected = currentValues.includes(option.value)
                  return (
                    <button
                      key={`${field.id}-${option.value}`}
                      type="button"
                      disabled={isSubmitted || isSubmitting}
                      onClick={() => setFormAnswers((current) => {
                        const existing = Array.isArray(current[field.id]) ? current[field.id] as string[] : []
                        const next = existing.includes(option.value)
                          ? existing.filter((value) => value !== option.value)
                          : [...existing, option.value]
                        return { ...current, [field.id]: next }
                      })}
                      className={cn(
                        'rounded-full px-3 py-2 text-sm',
                        surfaceButtonClassName(selected),
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span>{option.label}</span>
                        {renderSelectedIndicator(selected)}
                      </div>
                    </button>
                  )
                })}
                {supportsCustomOther(kind, field) ? (
                  <button
                    type="button"
                    disabled={isSubmitted || isSubmitting}
                    onClick={() => setFormAnswers((current) => {
                      const existing = Array.isArray(current[field.id]) ? current[field.id] as string[] : []
                      const next = existing.includes(OTHER_SELECTION_VALUE)
                        ? existing.filter((value) => value !== OTHER_SELECTION_VALUE)
                        : [...existing, OTHER_SELECTION_VALUE]
                      return { ...current, [field.id]: next }
                    })}
                    className={cn(
                      'rounded-full px-3 py-2 text-sm',
                      surfaceButtonClassName(
                        Array.isArray(formAnswers[field.id]) && formAnswers[field.id].includes(OTHER_SELECTION_VALUE),
                      ),
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span>{field.other_label || t('home.interaction.otherOption', 'Other')}</span>
                      {renderSelectedIndicator(Array.isArray(formAnswers[field.id]) && formAnswers[field.id].includes(OTHER_SELECTION_VALUE))}
                    </div>
                  </button>
                ) : null}
              </div>
            ) : null}
            {field.type === 'checkbox' && supportsCustomOther(kind, field) && Array.isArray(formAnswers[field.id]) && formAnswers[field.id].includes(OTHER_SELECTION_VALUE) ? (
              <Input
                id={`${requestId}-${field.id}`}
                aria-label={field.label}
                value={otherAnswers[field.id] || ''}
                disabled={isSubmitted || isSubmitting}
                placeholder={field.other_placeholder || field.placeholder || t('home.interaction.askUserPlaceholder', 'Type your response...')}
                onChange={(event) => setOtherAnswers((current) => ({ ...current, [field.id]: event.target.value }))}
                className="h-10 rounded-xl"
              />
            ) : null}
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <div className={cn('min-w-0 flex-1 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
          {isSubmitted ? (submittedLabel || t('home.interaction.submitted', 'Submitted')) : ''}
        </div>
        {!isSubmitted ? (
          <Button
            type="button"
            disabled={!canSubmit || isSubmitting}
            onClick={() => void handleSubmit()}
            variant="outline"
            className={submitButtonClassName()}
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {localizedSchema.submit_label || localizedSchema.submitLabel || t('home.interaction.continue', 'Continue')}
          </Button>
        ) : null}
      </div>
      <HomeDesignSystemPreviewDialog
        open={!!previewDesignSystem}
        onOpenChange={(open) => {
          if (!open) {
            setPreviewDesignSystem(null)
          }
        }}
        designSystem={previewDesignSystem}
        isDark={isDark}
      />
    </div>
  )
}
