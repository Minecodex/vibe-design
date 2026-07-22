const MODEL_ALIASES: Record<string, string> = {
  'flux': 'Flux',
  'gemini-3.1-flash-image-preview-official': 'Nano Banana 2',
  'nano-banana-2': 'Nano Banana 2',
  'gemini-3-pro-image-preview-official': 'Nano Banana Pro',
  'nano-banana-pro': 'Nano Banana Pro',
  'imagen-4.0-apimart': 'Imagen 4.0',
  'gpt-image-2': 'GPT-Image 2',
  'doubao-seedream-5-0': 'Seedream 5.0',
  'doubao-seedream-5-0-lite': 'Seedream 5.0 Lite',
  'doubao-seedream-4-5': 'Seedream 4.5',
  'doubao-seedance-2-0': 'Seedance 2.0',
  'doubao-seedance-1-5-pro': 'Seedance 1.5 Pro',
  'kling-v2-6': 'Kling 2.6',
  'kling-v3': 'Kling 3',
  'kling-v3-video-generation': 'Kling 3',
  'glm-5.1': 'GLM 5.1',
}

function normalizeModelToken(value: string | null | undefined): string {
  return String(value || '').trim().toLowerCase()
}

function resolveAliasedModelName(modelName: string): string | null {
  const exactMatch = MODEL_ALIASES[modelName]
  if (exactMatch) {
    return exactMatch
  }

  const strippedBuildSuffix = modelName.replace(/(?:-\d{4,})+$/, '')
  if (strippedBuildSuffix !== modelName) {
    return MODEL_ALIASES[strippedBuildSuffix] || null
  }

  return null
}

export function getModelDisplayName(
  modelLabel: string | null | undefined,
  modelName: string | null | undefined,
): string {
  const preferredLabel = String(modelLabel || '').trim()
  const normalizedLabel = normalizeModelToken(preferredLabel)
  const normalizedName = normalizeModelToken(modelName)

  if (preferredLabel && normalizedLabel !== normalizedName) {
    return preferredLabel
  }

  if (!normalizedName) {
    return preferredLabel
  }

  return resolveAliasedModelName(normalizedName) || String(modelName || '').trim()
}
