import * as React from 'react'
import { cn } from '@/lib/utils'

interface SegmentedControlOption<T extends string> {
  key: T
  label: React.ReactNode
  icon?: React.ComponentType<{ className?: string }>
  disabled?: boolean
}

function SegmentedControl<T extends string>({
  value,
  options,
  onValueChange,
  className,
  itemClassName,
  'aria-label': ariaLabel,
}: {
  value: T
  options: SegmentedControlOption<T>[]
  onValueChange: (value: T) => void
  className?: string
  itemClassName?: string
  'aria-label'?: string
}) {
  return (
    <div
      data-slot="segmented-control"
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        'inline-flex min-w-0 items-center gap-1 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-control-track)] p-1 shadow-[var(--app-shadow-control)] backdrop-blur-2xl',
        className
      )}
    >
      {options.map((option) => {
        const Icon = option.icon
        const selected = option.key === value
        return (
          <button
            key={option.key}
            type="button"
            role="tab"
            aria-selected={selected}
            disabled={option.disabled}
            onClick={() => onValueChange(option.key)}
            className={cn(
              'inline-flex h-9 min-w-[84px] items-center justify-center gap-2 rounded-[var(--app-radius-sm)] px-4 text-sm font-bold text-[var(--app-foreground-muted)] transition-all disabled:pointer-events-none disabled:opacity-50',
              'hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--app-focus-ring)]',
              selected && 'bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]',
              itemClassName
            )}
          >
            {Icon ? <Icon className="h-4 w-4" /> : null}
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export { SegmentedControl, type SegmentedControlOption }
