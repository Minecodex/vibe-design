import type { InteractionField, InteractionOption, InteractionQuestion } from '@/api/endpoints/agent'
import { getLocalizedKnownValueLabel } from './homeInteractionI18n'

type InteractionSchemaLike = {
  title?: string | null
  fields?: Array<InteractionField & { options?: InteractionOption[] }>
  questions?: Array<InteractionQuestion & { options?: InteractionOption[] }>
} | null | undefined

const KNOWN_VALUE_LABEL_FIELDS = new Set([
  'platform',
  'tone',
  'scale',
  'slide_count',
  'speaker_notes',
])

const QUICK_BRIEF_ORDER = [
  'output',
  'platform',
  'audience',
  'tone',
  'scale',
  'slide_count',
  'speaker_notes',
  'constraints',
]

function labelFromOptions(options: InteractionOption[] | undefined, value: string): string {
  const matched = (options || []).find((option) => option.value === value)
  return matched?.label || value
}

function labelForValue(
  fieldId: string,
  value: string,
  options: InteractionOption[] | undefined,
  language?: string,
): string {
  const normalizedValue = String(value || '').trim()
  if (!normalizedValue) {
    return ''
  }
  const fromOptions = labelFromOptions(options, normalizedValue)
  if (fromOptions !== normalizedValue) {
    return fromOptions
  }
  return getLocalizedKnownValueLabel(fieldId, normalizedValue, language) || normalizedValue
}

function formatFieldValue(
  field: (InteractionField & { options?: InteractionOption[] }) | undefined,
  value: unknown,
  fieldIdFallback = '',
  language?: string,
): string {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const source = value as Record<string, unknown>
    const label = String(source.label ?? '').trim()
    if (label) {
      return label
    }
    const rawValue = String(source.value ?? '').trim()
    if (rawValue) {
      return rawValue
    }
  }

  if (Array.isArray(value)) {
    return value
      .map((entry) => {
        if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
          const source = entry as Record<string, unknown>
          const label = String(source.label ?? '').trim()
          if (label) {
            return label
          }
          const rawValue = String(source.value ?? '').trim()
          if (rawValue) {
            return rawValue
          }
        }
        return labelForValue(field?.id || fieldIdFallback, String(entry || '').trim(), field?.options, language)
      })
      .filter(Boolean)
      .join(' / ')
  }

  const text = String(value ?? '').trim()
  if (!text) {
    return ''
  }

  if (
    field?.type === 'radio'
    || field?.type === 'select'
    || field?.type === 'cards'
    || field?.type === 'checkbox'
    || KNOWN_VALUE_LABEL_FIELDS.has(fieldIdFallback)
  ) {
    return labelForValue(field?.id || fieldIdFallback, text, field?.options, language)
  }

  return text
}

function buildQuickBriefSummaryFromAnswers(
  answers: Record<string, any>,
  schema?: InteractionSchemaLike,
  language?: string,
): string {
  const fieldsById = new Map((schema?.fields || []).map((field) => [field.id, field]))
  const orderedFieldIds = (schema?.fields || []).length > 0
    ? (schema?.fields || []).map((field) => field.id)
    : QUICK_BRIEF_ORDER
  const values = orderedFieldIds
    .map((fieldId) => formatFieldValue(fieldsById.get(fieldId), answers[fieldId], fieldId, language))
    .filter(Boolean)
  if (values.length > 0) {
    return values.join(' / ')
  }
  return ''
}

function buildQuestionSummaryFromAnswers(
  answers: Record<string, any>,
  schema?: InteractionSchemaLike,
  language?: string,
): string {
  const questions = schema?.questions || []
  const values = questions
    .map((question) => formatFieldValue(
      { id: question.id, label: question.header, type: question.type === 'input' ? 'text' : question.type === 'multiple' ? 'checkbox' : 'radio', options: question.options || [] } as InteractionField & { options?: InteractionOption[] },
      answers[question.id],
      question.id,
      language,
    ))
    .filter(Boolean)
  return values.join(' / ')
}

export function buildInteractionDisplayLabel(
  kind: string | undefined,
  schema: InteractionSchemaLike,
  answers: Record<string, any>,
  language?: string,
): string {
  if (kind === 'ask_user') {
    const questionSummary = buildQuestionSummaryFromAnswers(answers, schema, language)
    if (questionSummary) {
      return questionSummary
    }
  }

  if (kind === 'visual_direction_picker' || kind === 'design_system_picker') {
    const fieldId = kind === 'design_system_picker' ? 'design_system_id' : 'direction'
    const field = (schema?.fields || []).find((candidate) => candidate.id === fieldId)
    const value = formatFieldValue(field, answers[fieldId], fieldId, language)
    return value || 'Design system selected'
  }

  const quickBriefSummary = buildQuickBriefSummaryFromAnswers(answers, schema, language)
  if (quickBriefSummary) {
    return quickBriefSummary
  }

  const output = String(answers.output || '').trim()
  const audience = String(answers.audience || '').trim()
  if (output && audience) {
    return `${output} / ${audience}`
  }
  return output || audience || String(schema?.title || 'Submitted')
}

export function summarizeInteractionJsonContent(content: string, language?: string): string | null {
  const trimmed = String(content || '').trim()
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) {
    return null
  }

  try {
    const parsed = JSON.parse(trimmed)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null
    }
    const summary = buildQuickBriefSummaryFromAnswers(parsed as Record<string, any>, null, language)
    return summary || null
  } catch {
    return null
  }
}
