export interface HomeHarnessCritiqueFinding {
  role: string
  text: string
}

export interface HomeHarnessCritiqueDimension {
  role: string
  name: string
  score: number
  note: string
}

export interface HomeHarnessCritiqueWarning {
  code: string
  message: string
}

export interface HomeHarnessCritiqueState {
  critiqueRunId: string
  status: string
  displayStatus?: string | null
  round: number
  maxRounds: number
  scoreThreshold: number
  scoreScale: number
  composite: number | null
  scores: Record<string, number>
  dimensions: HomeHarnessCritiqueDimension[]
  findings: HomeHarnessCritiqueFinding[]
  warnings: HomeHarnessCritiqueWarning[]
  selectedRound: number | null
  selectedScore: number | null
  publishFallback: boolean
  reason: string | null
}

export interface HomeHarnessCritiqueProjectionEvent {
  type: 'critique.started'
    | 'critique.round_completed'
    | 'critique.protocol_rejected'
    | 'critique.shipped'
    | 'critique.below_threshold'
    | 'critique.degraded'
    | 'critique.failed'
  lane?: 'user' | 'internal'
  sequence?: number
  run_id?: string | null
  data: Record<string, any>
}

const CRITIQUE_EVENT_TYPES = new Set([
  'critique.started',
  'critique.round_completed',
  'critique.protocol_rejected',
  'critique.shipped',
  'critique.below_threshold',
  'critique.degraded',
  'critique.failed',
])

function numberOrNull(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function normalizeHomeHarnessCritiquePayload(raw: Record<string, any>): HomeHarnessCritiqueState {
  const rawScores = raw.scores && typeof raw.scores === 'object' && !Array.isArray(raw.scores)
    ? raw.scores as Record<string, unknown>
    : {}
  return {
    critiqueRunId: String(raw.critique_run_id ?? raw.critiqueRunId ?? ''),
    status: String(raw.status ?? 'running'),
    displayStatus: raw.display_status == null && raw.displayStatus == null
      ? null
      : String(raw.display_status ?? raw.displayStatus),
    round: numberOrNull(raw.round) ?? 0,
    maxRounds: numberOrNull(raw.max_rounds ?? raw.maxRounds) ?? 0,
    scoreThreshold: numberOrNull(raw.score_threshold ?? raw.scoreThreshold) ?? 0,
    scoreScale: numberOrNull(raw.score_scale ?? raw.scoreScale) ?? 10,
    composite: numberOrNull(raw.composite),
    scores: Object.fromEntries(
      Object.entries(rawScores)
        .map(([role, score]) => [role, numberOrNull(score)])
        .filter((entry): entry is [string, number] => entry[1] !== null),
    ),
    dimensions: (Array.isArray(raw.dimensions) ? raw.dimensions : []).map((item) => ({
      role: String(item?.role ?? ''),
      name: String(item?.name ?? ''),
      score: numberOrNull(item?.score) ?? 0,
      note: String(item?.note ?? ''),
    })),
    findings: (Array.isArray(raw.findings) ? raw.findings : []).map((item) => ({
      role: String(item?.role ?? ''),
      text: String(item?.text ?? ''),
    })).filter((item) => item.text),
    warnings: (Array.isArray(raw.warnings) ? raw.warnings : []).map((item) => ({
      code: String(item?.code ?? ''),
      message: String(item?.message ?? ''),
    })).filter((item) => item.message),
    selectedRound: numberOrNull(raw.selected_round ?? raw.selectedRound),
    selectedScore: numberOrNull(raw.selected_score ?? raw.selectedScore),
    publishFallback: Boolean(raw.publish_fallback ?? raw.publishFallback ?? false),
    reason: raw.reason == null ? null : String(raw.reason),
  }
}

export function applyHomeHarnessCritiqueEvent(
  current: HomeHarnessCritiqueState | null,
  event: { type: string; data?: Record<string, any> },
): HomeHarnessCritiqueState | null {
  if (!CRITIQUE_EVENT_TYPES.has(event.type)) {
    return current
  }
  return normalizeHomeHarnessCritiquePayload({
    ...(current ?? {}),
    ...(event.data ?? {}),
  })
}

export function hydrateHomeHarnessCritique(
  runtimeState: Record<string, any> | null | undefined,
): HomeHarnessCritiqueState | null {
  const raw = runtimeState?.critique
  return raw && typeof raw === 'object' && !Array.isArray(raw)
    ? normalizeHomeHarnessCritiquePayload(raw as Record<string, any>)
    : null
}
