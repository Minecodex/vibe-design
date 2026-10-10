import { AlertTriangle, CheckCircle2, Scale } from 'lucide-react'
import type { TFunction } from 'i18next'

import { cn } from '@/lib/utils'
import { isCritiqueVisible, resolveDesignJuryDimensionLabel } from './homeHarnessCritiqueDisplay'
import type { HomeHarnessCritiqueState } from '@/store/homeHarnessCritiqueProjection'

interface HomeHarnessCritiquePanelProps {
  critique: HomeHarnessCritiqueState | null
  isDark: boolean
  t: TFunction
}

const SCORE_ROLES = ['critic', 'brand', 'a11y', 'copy'] as const
const KNOWN_WARNING_CODES = new Set([
  'screenshot_unavailable',
  'screenshot_file_missing',
  'screenshot_file_type_unverified',
  'unknown_role',
  'score_clamped',
  'artifact_not_critiqueable',
])
const INTERNAL_WARNING_CODES = new Set(['composite_mismatch'])
export function HomeHarnessCritiquePanel({
  critique,
  isDark,
  t,
}: HomeHarnessCritiquePanelProps) {
  if (!isCritiqueVisible(critique)) return null

  const isBelowThreshold = critique.status === 'below_threshold' || critique.status === 'degraded'
  const isShipped = critique.status === 'shipped'
  const isFailed = critique.status === 'failed'
  const isRoundCompleted = critique.displayStatus === 'round_completed' || critique.status === 'completed'
  const isRunning = critique.status === 'running' && !isRoundCompleted
  const ScoreStatusIcon = isBelowThreshold || isFailed ? AlertTriangle : isShipped || isRoundCompleted ? CheckCircle2 : Scale
  const warnings = (critique.warnings ?? []).filter((warning) => !INTERNAL_WARNING_CODES.has(warning.code))
  const selectedBestRound = typeof critique.selectedRound === 'number' && critique.selectedRound > 0
    ? critique.selectedRound
    : null
  const selectedBestScore = typeof critique.selectedScore === 'number'
    ? critique.selectedScore
    : null
  const shouldShowRoundLimit = !isShipped
    && !isBelowThreshold
    && !isFailed
    && critique.maxRounds > critique.round

  return (
    <section
      data-testid="home-harness-critique-panel"
      className={cn(
        'app-floating-panel mb-4 rounded-2xl px-4 py-3',
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ScoreStatusIcon className={cn('h-4 w-4', isBelowThreshold || isFailed ? 'text-amber-500' : 'text-blue-500')} />
          <h3 className="text-sm font-medium">{t('home.chat.design_jury.title', 'Design Jury')}</h3>
        </div>
        <span className={cn('text-xs', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
          {t('home.chat.design_jury.round', 'Round {{round}}', {
            round: critique.round,
          })}
          {shouldShowRoundLimit ? (
            <span>
              {' · '}
              {t('home.chat.design_jury.round_limit', 'Up to {{maxRounds}} rounds', {
                maxRounds: critique.maxRounds,
              })}
            </span>
          ) : null}
        </span>
      </div>

      {isBelowThreshold ? (
        <p className="mt-2 text-xs text-amber-500">
          {selectedBestRound && selectedBestRound !== critique.round
            ? t('home.chat.design_jury.selected_best_published', 'Published round {{round}} as the best version, score {{score}}', {
              round: selectedBestRound,
              score: selectedBestScore ?? '-',
            })
            : t('home.chat.design_jury.best_published', 'Published the current best version')}
        </p>
      ) : null}

      {isRunning ? (
        <p className={cn('mt-2 text-xs', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
          {t('home.chat.design_jury.running', 'Quality check is running')}
        </p>
      ) : null}

      {isRoundCompleted ? (
        <p className={cn('mt-2 text-xs', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
          {t('home.chat.design_jury.round_completed', 'This quality-check round is complete')}
        </p>
      ) : null}

      {isFailed ? (
        <p className="mt-2 text-xs text-amber-500">
          {t('home.chat.design_jury.failed_published', 'Published with quality check warnings')}
        </p>
      ) : null}

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SCORE_ROLES.map((role) => (
          <div
            key={role}
            className="app-card-muted rounded-xl px-2.5 py-2"
          >
            <div className={cn('text-[11px]', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
              {t(`home.chat.design_jury.roles.${role}`, role)}
            </div>
            <div className="mt-1 text-sm font-medium">
              {critique.scores[role] ?? '-'} / {critique.scoreScale}
            </div>
          </div>
        ))}
      </div>

      {critique.dimensions.length > 0 ? (
        <div className={cn('mt-3 space-y-1 text-xs', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
          {critique.dimensions.map((dimension, index) => (
            <div key={`${dimension.role}:${dimension.name}:${index}`} className="flex items-center justify-between gap-3">
              <span className="truncate">
                {resolveDesignJuryDimensionLabel(dimension.name, t)}
              </span>
              <span className="shrink-0">{dimension.score} / {critique.scoreScale}</span>
            </div>
          ))}
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <div className="mt-3">
          <div className={cn('text-xs font-medium', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
            {t('home.chat.design_jury.warnings_title', 'Quality check notes')}
          </div>
          <ul className={cn('mt-1.5 space-y-1 text-xs', isDark ? 'text-amber-300/90' : 'text-amber-700')}>
            {warnings.map((warning, index) => {
              return (
                <li key={`${warning.code}:${warning.message}:${index}`}>
                  - {KNOWN_WARNING_CODES.has(warning.code)
                    ? t(`home.chat.design_jury.warnings.${warning.code}`, warning.message)
                    : warning.message}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}

      {critique.findings.length > 0 ? (
        <div className="mt-3">
          <div className={cn('text-xs font-medium', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
            {t('home.chat.design_jury.must_fix', 'MUST_FIX')}
          </div>
          <ul className={cn('mt-1.5 space-y-1 text-xs', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
            {critique.findings.map((finding, index) => (
              <li key={`${finding.role}:${finding.text}:${index}`}>- {finding.text}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
