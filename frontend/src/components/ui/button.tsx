import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-[var(--app-radius-sm)] text-sm font-semibold whitespace-nowrap transition-all outline-none focus-visible:border-[var(--app-primary)] focus-visible:ring-[3px] focus-visible:ring-[var(--app-focus-ring)] disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border border-[color-mix(in_srgb,var(--app-border)_78%,transparent)] bg-[var(--app-control)] text-foreground shadow-[var(--app-shadow-control)] hover:border-[var(--app-border-strong)] hover:bg-[var(--app-control-hover)] active:scale-[0.98]",
        primary:
          "border border-transparent bg-[var(--app-primary)] text-[var(--app-primary-foreground)] shadow-[inset_0_1px_0_var(--app-control-highlight),0_10px_26px_var(--app-tint-primary-hover)] hover:bg-[var(--app-primary-hover)] active:bg-[var(--app-primary-active)] active:scale-[0.98]",
        destructive:
          "border border-transparent bg-[var(--app-danger)] text-white shadow-[inset_0_1px_0_var(--app-control-highlight),0_10px_24px_var(--app-tint-danger)] hover:bg-[var(--app-danger-hover)] focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 active:scale-[0.98]",
        outline:
          "border border-[var(--app-border)] bg-transparent text-foreground shadow-none hover:border-[var(--app-border-strong)] hover:bg-[var(--app-control-hover)]",
        secondary:
          "border border-[var(--app-border)] bg-[var(--app-control)] text-foreground shadow-[var(--app-shadow-control)] hover:bg-[var(--app-control-hover)] active:scale-[0.98]",
        glass:
          "border border-[var(--app-border)] bg-[var(--app-glass)] text-foreground shadow-[var(--app-shadow-control)] backdrop-blur-2xl hover:bg-[var(--app-control-hover)] active:scale-[0.98]",
        media:
          "border border-[var(--app-media-control-light-border)] bg-[var(--app-media-control-light)] text-[var(--app-primary)] shadow-[var(--app-shadow-control)] backdrop-blur-2xl hover:border-[color-mix(in_srgb,var(--app-primary)_36%,var(--app-border))] hover:bg-[var(--app-media-control-light-hover)] active:scale-[0.98]",
        ghost:
          "border border-transparent bg-transparent shadow-none hover:bg-[var(--app-control-hover)] hover:text-foreground",
        link: "h-auto rounded-none p-0 text-[var(--app-primary)] underline-offset-4 shadow-none hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-[var(--app-radius-xs)] px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-[var(--app-radius-xs)] px-3 text-xs has-[>svg]:px-2.5",
        lg: "h-11 rounded-[var(--app-radius-sm)] px-6 has-[>svg]:px-4",
        icon: "size-9",
        "icon-xs": "size-6 rounded-[var(--app-radius-xs)] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({
  className,
  variant = "secondary",
  size = "default",
  asChild = false,
  ...props
}, ref) => {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      ref={ref}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
})
Button.displayName = "Button"

export { Button, buttonVariants }
