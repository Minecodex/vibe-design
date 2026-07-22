import * as React from 'react'
import { cn } from '@/lib/utils'

type AppSurfaceVariant = 'panel' | 'glass' | 'control' | 'muted' | 'media' | 'primaryTint' | 'successTint' | 'warningTint' | 'dangerTint'

const surfaceClasses: Record<AppSurfaceVariant, string> = {
  panel: 'border-[var(--app-border)] bg-[var(--app-surface)] shadow-[var(--app-shadow-panel)]',
  glass: 'border-[var(--app-border)] bg-[var(--app-glass)] shadow-[var(--app-shadow-panel)] backdrop-blur-2xl',
  control: 'border-[var(--app-border)] bg-[var(--app-control)] shadow-[var(--app-shadow-control)]',
  muted: 'border-[var(--app-border)] bg-[var(--app-surface-muted)]',
  media: 'border-[var(--app-media-border)] bg-[var(--app-media-overlay)] shadow-[var(--app-shadow-panel)]',
  primaryTint: 'border-[color-mix(in_srgb,var(--app-primary)_24%,var(--app-border))] bg-[var(--app-tint-primary)]',
  successTint: 'border-[color-mix(in_srgb,var(--app-success)_24%,var(--app-border))] bg-[var(--app-tint-success)]',
  warningTint: 'border-[color-mix(in_srgb,var(--app-warning)_24%,var(--app-border))] bg-[var(--app-tint-warning)]',
  dangerTint: 'border-[color-mix(in_srgb,var(--app-danger)_24%,var(--app-border))] bg-[var(--app-tint-danger)]',
}

function AppSurface({
  className,
  variant = 'panel',
  ...props
}: React.ComponentProps<'div'> & {
  variant?: AppSurfaceVariant
}) {
  return (
    <div
      data-slot="app-surface"
      data-variant={variant}
      className={cn('rounded-[var(--app-radius-lg)] border text-foreground', surfaceClasses[variant], className)}
      {...props}
    />
  )
}

export { AppSurface, type AppSurfaceVariant }
