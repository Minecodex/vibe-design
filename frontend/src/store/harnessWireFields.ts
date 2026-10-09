export function wireRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
}

export function wireString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : undefined
}

export function wireNullableString(value: unknown): string | null {
  return wireString(value) ?? null
}

export function wireId(value: unknown): string | number | undefined {
  return typeof value === 'string' || typeof value === 'number' ? value : undefined
}
