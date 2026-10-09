import type { ModelRead } from '@/api/endpoints/providers'

// Built-in registry rows have model-name keys; only persisted rows have API IDs.
export type ProviderModelView = Omit<ModelRead, 'id'> & { id: number | string }
