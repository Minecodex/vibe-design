import * as React from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const IconButton = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof Button>
>(({
  className,
  size = 'icon',
  variant = 'ghost',
  ...props
}, ref) => {
  return (
    <Button
      ref={ref}
      data-slot="icon-button"
      size={size}
      variant={variant}
      className={cn('rounded-full', className)}
      {...props}
    />
  )
})
IconButton.displayName = 'IconButton'

export { IconButton }
