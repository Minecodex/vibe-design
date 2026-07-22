import * as React from 'react'
import { cn } from '@/lib/utils'
import { AppSurface } from './AppSurface'

function EmptyState({
  icon,
  title,
  description,
  className,
  children,
}: {
  icon?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
  className?: string
  children?: React.ReactNode
}) {
  return (
    <div className={cn('flex min-h-[320px] w-full flex-col items-center justify-center text-center', className)}>
      {icon ? (
        <AppSurface variant="muted" className="mb-4 flex h-16 w-16 items-center justify-center rounded-[var(--app-radius-lg)] text-[var(--app-foreground-subtle)]">
          {icon}
        </AppSurface>
      ) : null}
      <p className="text-lg font-semibold text-foreground">{title}</p>
      {description ? <p className="mt-2 max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {children ? <div className="mt-4">{children}</div> : null}
    </div>
  )
}

export { EmptyState }
