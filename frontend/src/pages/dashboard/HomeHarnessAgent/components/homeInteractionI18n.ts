import type { InteractionField, InteractionOption, InteractionQuestion } from '@/api/endpoints/agent'

type Language = string | null | undefined

type InteractionSchemaLike = {
  title?: string | null
  description?: string | null
  submit_label?: string | null
  submitLabel?: string | null
  fields?: Array<InteractionField & { options?: InteractionOption[] }>
  questions?: Array<InteractionQuestion & { options?: InteractionOption[] }>
} | null | undefined

type LocalizedFieldCopy = {
  label?: string
  placeholder?: string
}

const QUICK_BRIEF_COPY = {
  zh: {
    title: '快速说明',
    description: '先锁定这次产出的关键约束，后面的大纲、方向和执行都会基于这里的答案。',
    submitLabel: '提交',
    fields: {
      output: { label: '这次要产出什么', placeholder: '例如：PowerPoint 演示文稿' },
      platform: { label: '发布平台 / 使用场景' },
      audience: { label: '目标受众', placeholder: '例如：潜在客户 / 管理层 / 投资人' },
      tone: { label: '希望的语气与气质' },
      scale: { label: '范围 / 规模' },
      constraints: { label: '必须遵守的约束', placeholder: '例如：移动端优先、必须双语、要突出价格信息' },
      speaker_notes: { label: '讲稿备注需要到什么程度' },
      slide_count: { label: '页数范围' },
      brand_context: { label: '品牌基础情况', placeholder: '例如：已有品牌规范 / 有参考站 / 暂时没有' },
      device_scope: { label: '设备范围' },
      page_or_screen_count: { label: '页面 / 屏数' },
      doc_depth: { label: '文档深度' },
      tone_of_writing: { label: '写作语气' },
    },
  },
  en: {
    title: 'Quick brief',
    description: 'Lock the key constraints for this request before planning and execution.',
    submitLabel: 'Submit',
    fields: {
      output: { label: 'What should we make?', placeholder: 'For example: PowerPoint deck' },
      platform: { label: 'Platform / use case' },
      audience: { label: 'Target audience', placeholder: 'For example: prospects / leadership / investors' },
      tone: { label: 'Tone and overall feel' },
      scale: { label: 'Scope / scale' },
      constraints: { label: 'Constraints to respect', placeholder: 'For example: mobile first, bilingual, highlight pricing' },
      speaker_notes: { label: 'How detailed should speaker notes be?' },
      slide_count: { label: 'Slide count' },
      brand_context: { label: 'Brand context', placeholder: 'For example: brand guidelines / reference sites / no brand yet' },
      device_scope: { label: 'Device scope' },
      page_or_screen_count: { label: 'Page / screen count' },
      doc_depth: { label: 'Document depth' },
      tone_of_writing: { label: 'Writing tone' },
    },
  },
} as const

const DESIGN_SYSTEM_COPY = {
  zh: {
    title: '选择设计体系',
    description: '如果你还没有明确品牌体系，请先选择一个设计体系，我们会基于它继续规划。',
    submitLabel: '确认设计体系',
    fields: {
      design_system_id: { label: '设计体系' },
    },
  },
  en: {
    title: 'Choose a design system',
    description: 'If you do not have a brand system yet, choose a design system before we continue.',
    submitLabel: 'Confirm design system',
    fields: {
      design_system_id: { label: 'Design system' },
    },
  },
} as const

const OPTION_LABELS: Record<string, { zh: string, en: string }> = {
  live_presentation: { zh: '线下演讲', en: 'Live presentation' },
  sales_pitch: { zh: '销售提案', en: 'Sales pitch' },
  internal_review: { zh: '内部汇报', en: 'Internal review' },
  professional_restrained: { zh: '专业克制', en: 'Professional and restrained' },
  confident_modern: { zh: '自信现代', en: 'Confident and modern' },
  warm_approachable: { zh: '温暖亲和', en: 'Warm and approachable' },
  premium_confident: { zh: '高级品牌感', en: 'Premium and confident' },
  none: { zh: '不需要', en: 'No notes' },
  light: { zh: '简要提示', en: 'Light notes' },
  detailed: { zh: '详细备注', en: 'Detailed notes' },
  '5_8': { zh: '5-8', en: '5-8' },
  '10_15': { zh: '10-15', en: '10-15' },
  '15_plus': { zh: '15+', en: '15+' },
} as const

function getLocale(language: Language): 'zh' | 'en' {
  return String(language || '').toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

function localizeOption(option: InteractionOption, language: Language): InteractionOption {
  const locale = getLocale(language)
  const override = OPTION_LABELS[option.value]
  return {
    ...option,
    label: override?.[locale] || option.label,
  }
}

export function localizeInteractionSchema(
  kind: string | undefined,
  schema: InteractionSchemaLike,
  language: Language,
): InteractionSchemaLike {
  if (!schema) {
    return schema
  }

  const locale = getLocale(language)
  const quickBriefCopy = QUICK_BRIEF_COPY[locale]
  const designSystemCopy = DESIGN_SYSTEM_COPY[locale]
  const activeCopy = kind === 'quick_brief'
    ? quickBriefCopy
    : kind === 'design_system_picker'
      ? designSystemCopy
      : null

  return {
    ...schema,
    title: kind === 'quick_brief'
      ? schema.title || quickBriefCopy.title
      : kind === 'design_system_picker'
        ? schema.title || designSystemCopy.title
        : schema.title,
    description: kind === 'quick_brief'
      ? schema.description || quickBriefCopy.description
      : kind === 'design_system_picker'
        ? schema.description || designSystemCopy.description
        : schema.description,
    submit_label: kind === 'quick_brief'
      ? schema.submit_label || quickBriefCopy.submitLabel
      : kind === 'design_system_picker'
        ? schema.submit_label || designSystemCopy.submitLabel
      : schema.submit_label,
    submitLabel: kind === 'quick_brief'
      ? schema.submitLabel || schema.submit_label || quickBriefCopy.submitLabel
      : kind === 'design_system_picker'
        ? schema.submitLabel || schema.submit_label || designSystemCopy.submitLabel
      : schema.submitLabel,
    fields: (schema.fields || []).map((field) => {
      const fieldCopies = activeCopy?.fields as Record<string, LocalizedFieldCopy> | undefined
      const fieldCopy = fieldCopies?.[field.id]
      const label = String(field.label || fieldCopy?.label || field.id).trim() || field.id
      return {
        ...field,
        label,
        placeholder: field.placeholder ?? fieldCopy?.placeholder ?? null,
        options: (field.options || []).map((option) => localizeOption(option, language)),
      }
    }),
    questions: (schema.questions || []).map((question) => ({
      ...question,
      options: (question.options || []).map((option) => localizeOption(option, language)),
    })),
  }
}

export function getLocalizedKnownValueLabel(
  _fieldId: string,
  value: string,
  language: Language,
): string | null {
  const locale = getLocale(language)
  return OPTION_LABELS[value]?.[locale] || null
}
