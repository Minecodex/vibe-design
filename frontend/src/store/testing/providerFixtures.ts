import type { ModelRead, ProviderRegistryEntry, ProviderStatus } from '@/api/endpoints/providers'
import { httpResponse } from './harnessStateFixtures'

export function providerListResponse(value: { data: Array<Partial<ProviderStatus> & Pick<ProviderStatus, 'code' | 'name' | 'status'>> }) {
  return httpResponse({ data: value.data.map((provider): ProviderStatus => ({
    author: '', description: '', logo_url: '', tags: [], credential_count: 0, model_count: 0,
    ...provider,
  })) })
}

export function providerRegistryResponse(value: { data: Record<string, Pick<ProviderRegistryEntry, 'models'> & Partial<ProviderRegistryEntry>> }) {
  return httpResponse({ data: Object.fromEntries(Object.entries(value.data).map(([key, provider]) => [key, {
    credential_types: [], requires_endpoint: false, ...provider,
  }])) })
}

export function providerModelsResponse(value: { data: Array<Partial<ModelRead> & Pick<ModelRead, 'model_name' | 'model_type' | 'is_enabled'>> }) {
  return httpResponse({ data: value.data.map((model): ModelRead => ({
    id: 0, provider_code: 'builtin', credential_id: null, endpoint: null, ...model,
  })) })
}
