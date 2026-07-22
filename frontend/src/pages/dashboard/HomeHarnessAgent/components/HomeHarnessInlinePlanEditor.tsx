import { useEffect, useMemo, useState } from 'react'
import type { TFunction } from 'i18next'
import { ArrowDown, ArrowUp, Pencil, Plus, Save, Trash2, X } from 'lucide-react'

import type { ExecutionStepRead, UserPlanOutlineItemRead, UserPlanRead } from '@/api/endpoints/agent'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface HomeHarnessInlinePlanEditorProps {
  plan: UserPlanRead
  isDark: boolean
  t: TFunction
  isSubmitting?: boolean
  onStartExecution?: () => Promise<void>
  onRevisePlan: (instruction: string) => Promise<void>
  onPatchCurrentOutline: (plan: UserPlanRead) => Promise<void>
}

function clonePlan(plan: UserPlanRead): UserPlanRead {
  return {
    ...plan,
    items: Array.isArray(plan.items) ? plan.items.map((item) => ({ ...item })) : [],
    constraints: Array.isArray(plan.constraints) ? [...plan.constraints] : [],
    style_notes: Array.isArray(plan.style_notes) ? [...plan.style_notes] : [],
  }
}

function normalizeOutlineItemForDraft(item: UserPlanOutlineItemRead, index: number): UserPlanOutlineItemRead {
  return {
    id: item.id || `item-${index + 1}`,
    title: String(item.title || ''),
    summary: item.summary ?? item.description ?? null,
    description: item.description ?? item.summary ?? null,
    order: item.order ?? index + 1,
    file_path: item.file_path ?? null,
    file_name: item.file_name ?? null,
    artifact_ref: item.artifact_ref ?? null,
  }
}

function normalizeDraftItems(plan: UserPlanRead): UserPlanOutlineItemRead[] {
  if (Array.isArray(plan.items) && plan.items.length > 0) {
    return plan.items.map(normalizeOutlineItemForDraft)
  }
  const items = Array.isArray(plan.outline) ? plan.outline : []
  return items.map(normalizeOutlineItemForDraft)
}

function buildPatchedPlan(basePlan: UserPlanRead, items: UserPlanOutlineItemRead[]): UserPlanRead {
  const normalizedItems = items.map((item, index) => normalizeOutlineItemForDraft({ ...item, order: index + 1 }, index))
  return {
    ...basePlan,
    items: normalizedItems,
    outline: normalizedItems,
  }
}

function isPlanReadonly(plan: UserPlanRead): boolean {
  const executionStatus = String(plan.execution_state?.status || plan.projection_state?.status || '').toLowerCase()
  return Boolean(
    plan.readonly
    || plan.projection_state?.readonly
    || ['executing', 'in_progress', 'running', 'finalizing', 'completed', 'failed', 'blocked', 'cancelled', 'canceled'].includes(executionStatus),
  )
}

function shouldShowReadonlyHint(plan: UserPlanRead): boolean {
  const executionStatus = String(plan.execution_state?.status || plan.projection_state?.status || '').toLowerCase()
  return ['executing', 'in_progress', 'running', 'finalizing'].includes(executionStatus)
}

function executionStepsForPlan(plan: UserPlanRead): ExecutionStepRead[] {
  const directSteps = plan.execution_state?.steps
  if (Array.isArray(directSteps) && directSteps.length > 0) {
    return directSteps
  }
  const projectedSteps = plan.projection_state?.execution_steps
  return Array.isArray(projectedSteps) ? projectedSteps : []
}

function labelForStatus(t: TFunction, status?: string | null): string {
  const normalized = String(status || 'pending').toLowerCase()
  if (normalized === 'in_progress' || normalized === 'executing') {
    return t('home.planReview.inline.status.inProgress', 'In progress')
  }
  if (normalized === 'completed' || normalized === 'done') {
    return t('home.planReview.inline.status.completed', 'Completed')
  }
  if (normalized === 'failed' || normalized === 'blocked') {
    return t('home.planReview.inline.status.blocked', 'Needs attention')
  }
  return t('home.planReview.inline.status.pending', 'Pending')
}

export function HomeHarnessInlinePlanEditor({
  plan,
  isDark,
  t,
  isSubmitting = false,
  onStartExecution,
  onRevisePlan,
  onPatchCurrentOutline,
}: HomeHarnessInlinePlanEditorProps) {
  const activePlan = useMemo(() => clonePlan(plan), [plan])
  const [instruction, setInstruction] = useState('')
  const [draftPlan, setDraftPlan] = useState<UserPlanRead>(activePlan)
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editingDraft, setEditingDraft] = useState<{ title: string; summary: string }>({ title: '', summary: '' })
  const [aiEditorOpen, setAiEditorOpen] = useState(false)

  useEffect(() => {
    setDraftPlan(activePlan)
    setEditingItemId(null)
    setEditingDraft({ title: '', summary: '' })
    setInstruction('')
    setAiEditorOpen(false)
  }, [activePlan])

  const draftItems = useMemo(() => normalizeDraftItems(draftPlan), [draftPlan])
  const readonly = isPlanReadonly(plan)
  const showReadonlyHint = shouldShowReadonlyHint(plan)
  const executionSteps = useMemo(() => executionStepsForPlan(plan), [plan])
  const currentStep = executionSteps.find((step) => String(step.status || '').toLowerCase() === 'in_progress')
  const isManualEditing = editingItemId !== null
  const interactionLocked = readonly || isSubmitting || aiEditorOpen || isManualEditing

  const beginManualEdit = (item: UserPlanOutlineItemRead) => {
    if (readonly || isSubmitting || aiEditorOpen) {
      return
    }
    setEditingItemId(String(item.id))
    setEditingDraft({
      title: String(item.title || ''),
      summary: String(item.summary || item.description || ''),
    })
  }

  const cancelManualEdit = () => {
    setEditingItemId(null)
    setEditingDraft({ title: '', summary: '' })
  }

  const saveManualEdit = async () => {
    if (!editingItemId || readonly || isSubmitting) {
      return
    }
    const nextPlan = buildPatchedPlan(
      draftPlan,
      draftItems.map((item) => (
        String(item.id) === editingItemId
          ? { ...item, title: editingDraft.title, summary: editingDraft.summary, description: editingDraft.summary }
          : item
      )),
    )
    await onPatchCurrentOutline(nextPlan)
    cancelManualEdit()
  }

  const moveItem = async (index: number, direction: -1 | 1) => {
    if (interactionLocked) {
      return
    }
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= draftItems.length) {
      return
    }
    const next = [...draftItems]
    ;[next[index], next[targetIndex]] = [next[targetIndex], next[index]]
    await onPatchCurrentOutline(buildPatchedPlan(draftPlan, next))
  }

  const deleteItem = async (index: number) => {
    if (interactionLocked) {
      return
    }
    await onPatchCurrentOutline(buildPatchedPlan(draftPlan, draftItems.filter((_, currentIndex) => currentIndex !== index)))
  }

  const addItem = () => {
    if (interactionLocked) {
      return
    }
    const nextItem = {
      id: `item-${Date.now()}`,
      title: t('home.planReview.inline.newItemTitle', 'New item'),
      summary: '',
      description: '',
      order: draftItems.length + 1,
    }
    setDraftPlan(buildPatchedPlan(draftPlan, [...draftItems, nextItem]))
    setEditingItemId(nextItem.id)
    setEditingDraft({ title: nextItem.title, summary: '' })
  }

  const handleSubmitRevision = async () => {
    const nextInstruction = instruction.trim()
    if (!nextInstruction || readonly || isSubmitting || isManualEditing) {
      return
    }
    await onRevisePlan(nextInstruction)
  }

  return (
    <div className="space-y-3">
      {showReadonlyHint ? (
        <div
          className={cn(
            'rounded-2xl border px-4 py-3 text-sm',
            isDark
              ? 'border-amber-300/20 bg-amber-300/10 text-amber-100'
              : 'border-amber-200 bg-amber-50 text-amber-900',
          )}
        >
          {t('home.planReview.inline.readonlyHint', 'The current plan is executing. Regenerate a new plan if you need to change the outline.')}
        </div>
      ) : null}

      <div className="space-y-2">
        {draftItems.map((item, index) => {
          const itemId = String(item.id || index)
          const isEditing = editingItemId === itemId
          const hoverActionsVisible = !readonly && !aiEditorOpen && !isManualEditing && !isSubmitting

          return (
            <div
              key={itemId}
              className={cn(
                'app-card-muted group rounded-2xl px-4 py-3 transition-colors',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {isEditing ? (
                    <div className="space-y-3">
                      <input
                        value={editingDraft.title}
                        onChange={(event) => setEditingDraft((current) => ({ ...current, title: event.target.value }))}
                        placeholder={t('home.planReview.inline.itemTitlePlaceholder', 'Outline title')}
                        className={cn(
                          'w-full rounded-xl border border-[var(--app-border)] bg-[var(--app-control)] px-3 py-2 text-sm text-[var(--app-foreground)] outline-none transition-colors placeholder:text-[var(--app-foreground-subtle)] focus:border-[var(--app-primary)] focus:ring-2 focus:ring-[var(--app-focus-ring)]',
                        )}
                      />
                      <textarea
                        value={editingDraft.summary}
                        onChange={(event) => setEditingDraft((current) => ({ ...current, summary: event.target.value }))}
                        placeholder={t('home.planReview.inline.itemSummaryPlaceholder', 'Describe what this item should contain')}
                        className={cn(
                          'min-h-[96px] w-full rounded-xl border border-[var(--app-border)] bg-[var(--app-control)] px-3 py-2 text-sm text-[var(--app-foreground)] outline-none transition-colors placeholder:text-[var(--app-foreground-subtle)] focus:border-[var(--app-primary)] focus:ring-2 focus:ring-[var(--app-focus-ring)]',
                        )}
                      />
                      <div className="flex items-center justify-end gap-2">
                        <Button type="button" variant="outline" onClick={cancelManualEdit} disabled={isSubmitting}>
                          {t('home.planReview.inline.cancelEdit', 'Cancel')}
                        </Button>
                        <Button type="button" onClick={() => void saveManualEdit()} disabled={!editingDraft.title.trim() || isSubmitting}>
                          <Save className="mr-2 h-4 w-4" />
                          {t('home.planReview.inline.saveEdit', 'Save')}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
                        {String(item.title || '')}
                      </div>
                      {item.summary || item.description ? (
                        <div className={cn('mt-1 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                          {String(item.summary || item.description || '')}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>

                {!isEditing && hoverActionsVisible ? (
                  <div className={cn(
                    'flex shrink-0 items-center gap-1 transition-opacity',
                    'opacity-100 sm:opacity-0 sm:group-hover:opacity-100',
                  )}>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('home.planReview.inline.editItem', 'Edit item')}
                      onClick={() => beginManualEdit(item)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('home.planReview.inline.moveUp', 'Move item up')}
                      disabled={index === 0}
                      onClick={() => void moveItem(index, -1)}
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('home.planReview.inline.moveDown', 'Move item down')}
                      disabled={index === draftItems.length - 1}
                      onClick={() => void moveItem(index, 1)}
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('home.planReview.inline.deleteItem', 'Delete item')}
                      onClick={() => void deleteItem(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>

      {!readonly && !aiEditorOpen && !isManualEditing ? (
        <div className="flex justify-end">
          <Button type="button" variant="outline" onClick={addItem} disabled={isSubmitting}>
            <Plus className="mr-2 h-4 w-4" />
            {t('home.planReview.inline.addItem', 'Add item')}
          </Button>
        </div>
      ) : null}

      {!readonly && aiEditorOpen ? (
        <div
          className={cn(
            'app-card-muted space-y-3 rounded-2xl px-4 py-4',
          )}
        >
          <div>
            <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
              {t('home.planReview.inline.nlTitle', 'Modify with natural language')}
            </div>
            <div className={cn('mt-1 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
              {t(
                'home.planReview.inline.nlHint',
                'Describe how you want the outline to change. The AI will rewrite the outline before execution starts.',
              )}
            </div>
          </div>
          <textarea
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder={t(
              'home.planReview.inline.nlPlaceholder',
              'Describe how you want the outline to change...',
            )}
            className={cn(
              'min-h-[110px] w-full rounded-2xl border border-[var(--app-border)] bg-[var(--app-control)] px-4 py-3 text-sm text-[var(--app-foreground)] outline-none transition-colors placeholder:text-[var(--app-foreground-subtle)] focus:border-[var(--app-primary)] focus:ring-2 focus:ring-[var(--app-focus-ring)]',
            )}
          />
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => { setAiEditorOpen(false); setInstruction('') }} disabled={isSubmitting}>
              <X className="mr-2 h-4 w-4" />
              {t('home.planReview.inline.cancelAiEdit', 'Cancel')}
            </Button>
            <Button type="button" onClick={() => void handleSubmitRevision()} disabled={!instruction.trim() || isSubmitting}>
              {t('home.planReview.inline.applyRevision', 'Apply revision request')}
            </Button>
          </div>
        </div>
      ) : null}

      <details
        className={cn(
          'app-card-muted rounded-2xl px-4 py-3',
        )}
      >
        <summary className={cn('cursor-pointer text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
          {t('home.planReview.inline.executionDetails', 'Internal execution details')}
          {currentStep ? (
            <span className={cn('ml-2 text-xs font-normal', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
              {t('home.planReview.inline.currentStep', 'Current')}: {String(currentStep.title || currentStep.id)}
            </span>
          ) : null}
        </summary>
        <div className="mt-3 space-y-2">
          {executionSteps.length > 0 ? executionSteps.map((step, index) => (
            <div
              key={String(step.id || index)}
              className={cn(
                'rounded-xl bg-[var(--app-control)] px-3 py-2 text-xs text-[var(--app-foreground-muted)]',
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium">{String(step.title || step.id || '')}</span>
                <span className={isDark ? 'text-zinc-500' : 'text-zinc-500'}>{labelForStatus(t, step.status)}</span>
              </div>
              {step.progress_message || step.description ? (
                <div className={cn('mt-1 leading-5', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {String(step.progress_message || step.description || '')}
                </div>
              ) : null}
            </div>
          )) : (
            <div className={cn('text-xs', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
              {t('home.planReview.inline.noExecutionSteps', 'Execution steps will appear after the outline is compiled.')}
            </div>
          )}
        </div>
      </details>

      <div
        className={cn(
          'app-divider flex flex-wrap items-center justify-end gap-3 border-t pt-3',
        )}
      >
        {!readonly ? (
          <>
            <Button type="button" variant="outline" onClick={() => setAiEditorOpen(true)} disabled={isSubmitting || isManualEditing || aiEditorOpen}>
              {t('home.planReview.adjustOutline', 'Adjust outline')}
            </Button>
            <Button type="button" onClick={() => void onStartExecution?.()} disabled={isSubmitting || isManualEditing || aiEditorOpen}>
              {t('home.planReview.startExecution', 'Start execution')}
            </Button>
          </>
        ) : null}
      </div>
    </div>
  )
}
