const PROMPT_EXTRACTOR_MODEL_LABELS = new Map<string, string>([
  ['gemini31pro', 'Gemini 3.1 Pro'],
  ['gemini31propreview', 'Gemini 3.1 Pro'],
])

function normalizeModelKey(model: string): string {
  return model.toLowerCase().replace(/[^a-z0-9]+/g, '')
}

export function getPromptExtractorModelLabel(model: string | null | undefined): string {
  const rawModel = String(model || '').trim()
  if (!rawModel) {
    return 'Gemini 3.1 Pro'
  }

  return PROMPT_EXTRACTOR_MODEL_LABELS.get(normalizeModelKey(rawModel)) || rawModel
}
