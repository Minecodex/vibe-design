export type AgentMediaVariant = 'thumb-256' | 'thumb-512' | 'thumb-1024' | 'original'

export type AgentHeavyBlockRenderMode = 'compact' | 'full'

export interface AgentRenderWeightSnapshot {
  itemCount: number
  totalWeight: number
  heavyItemCount: number
}

export function getAgentMediaVariantWidth(variant: AgentMediaVariant | undefined): number | undefined {
  switch (variant) {
    case 'thumb-256':
      return 256
    case 'thumb-512':
      return 512
    case 'thumb-1024':
      return 1024
    default:
      return undefined
  }
}
