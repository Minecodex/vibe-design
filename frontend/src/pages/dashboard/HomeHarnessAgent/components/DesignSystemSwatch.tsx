import { cn } from '@/lib/utils'
import type { HarnessDesignSystemRead } from '@/api/endpoints/agent'
import { getDesignSystemPalette } from './homeDesignSystemPreviewUtils'

export function DesignSystemSwatch({
  designSystem,
  className,
}: {
  designSystem: Pick<HarnessDesignSystemRead, 'id' | 'palette'> | null | undefined
  isDark: boolean
  className?: string
}) {
  const palette = getDesignSystemPalette(designSystem)
  return (
    <div
      data-testid={designSystem?.id ? `home-design-system-swatch-${designSystem.id}` : 'home-design-system-swatch-auto'}
      className={cn(
        'grid h-10 w-10 shrink-0 grid-cols-2 overflow-hidden rounded-xl border shadow-sm',
        'app-card',
        className,
      )}
    >
      {palette.map((color, index) => (
        <span key={`${color}-${index}`} style={{ backgroundColor: color }} />
      ))}
    </div>
  )
}
