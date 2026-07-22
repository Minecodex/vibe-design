import * as React from 'react'
import { cn } from '@/lib/utils'
import { AppSurface } from './AppSurface'

function GlassPanel({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <AppSurface
      variant="glass"
      data-slot="glass-panel"
      className={cn('backdrop-blur-2xl', className)}
      {...props}
    />
  )
}

export { GlassPanel }
