import * as React from 'react'
import { cn } from '@/lib/utils'

type StatusBadgeVariant = 'default' | 'primary' | 'success' | 'warning' | 'danger'

const badgeClasses: Record<StatusBadgeVariant, string> = {
  default: 'bg-[var(--app-surface-muted)] text-[var(--app-foreground-muted)]',
  primary: 'bg-[var(--app-tint-primary)] text-[var(--app-primary)]',
  success: 'bg-[var(--app-tint-success)] text-[var(--app-success)]',
  warning: 'bg-[var(--app-tint-warning)] text-[var(--app-warning)]',
  danger: 'bg-[var(--app-tint-danger)] text-[var(--app-danger)]',
}

function StatusBadge({
  className,
  variant = 'default',
  ...props
}: React.ComponentProps<'span'> & {
  variant?: StatusBadgeVariant
}) {
  return (
    <span
      data-slot="status-badge"
      data-variant={variant}
      className={cn('inline-flex min-h-6 items-center rounded-full px-2.5 text-[11px] font-bold', badgeClasses[variant], className)}
      {...props}
    />
  )
}

export { StatusBadge, type StatusBadgeVariant }
