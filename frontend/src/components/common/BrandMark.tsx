import { cn } from '@/lib/utils'

interface BrandMarkProps {
  isDark: boolean
  className?: string
  label?: string
}

export function BrandMark({
  isDark,
  className,
  label = 'brand-mark',
}: BrandMarkProps) {
  return (
    <div
      aria-label={label}
      className={cn(
        'flex items-center justify-center rounded-lg text-base font-bold shadow-sm',
        isDark ? 'bg-white text-black' : 'bg-black text-white',
        className,
      )}
    >
      M
    </div>
  )
}
