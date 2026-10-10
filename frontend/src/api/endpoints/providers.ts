import { apiClient } from '../client'

export interface ProviderStatus {
    code: string
    name: string
    author: string
    description: string
    logo_url: string
    tags: string[]
    status: 'installable' | 'unauthorized' | 'authorized'
    credential_count: number
    model_count: number
    is_builtin?: boolean
}

export interface CredentialRead {
    id: number
    provider_code: string
    name: string
    access_key_hint: string
    auth_type: string
}

export interface CredentialCreate {
    name: string
    access_key: string
    secret_key?: string
    auth_type?: string
}

export interface CredentialUpdate {
    name?: string
    access_key?: string
    secret_key?: string
}

export interface ModelRead {
    id: number
    provider_code: string
    model_name: string
    model_type: string
    is_enabled: boolean
    credential_id: number | null
    endpoint: string | null
}

export interface ModelCreate {
    model_name: string
    model_type: string
    credential_id?: number | null
    endpoint?: string | null
}

export interface ModelUpdate {
    is_enabled?: boolean
    credential_id?: number | null
}

export interface ModelOption {
    model_name: string
    label: string
    description?: string
    config?: {
        pricing_cents?: Record<string, number>
        pricing_mode?: 'per_resolution' | 'flat' | 'per_second' | 'per_token'
        allowed_sizes?: string[]
        allowed_durations?: string[]
        allowed_aspect_ratios?: string[]
        dimension_table?: Record<string, Record<string, { width?: number | null; height?: number | null }>>
        dimension_policy?: string
        dimension_source?: string
        max_input_tokens?: number
        max_output_tokens?: number
        supports_thinking_mode?: boolean
        supports_fast_mode?: boolean
        thinking_variant_of?: string
        [key: string]: unknown
    }
}

export interface ProviderRegistryEntry {
    models: Record<string, ModelOption[]>
    text2image?: ModelOption[]
    text2video?: ModelOption[]
    multimodal?: ModelOption[]
    credential_types: string[]
    requires_endpoint: boolean
    is_builtin?: boolean
}

export type ModelRegistry = Record<string, ProviderRegistryEntry>

export const providersApi = {
    // Provider overview
    list: () => apiClient.get<ProviderStatus[]>('/providers'),
    getRegistry: () => apiClient.get<ModelRegistry>('/providers/registry'),

    // Install / uninstall
    install: (code: string) => apiClient.post<{ message: string }>(`/providers/${code}/install`),
    uninstall: (code: string) => apiClient.delete<{ message: string }>(`/providers/${code}/uninstall`),

    // Credentials
    listCredentials: (code: string) => apiClient.get<CredentialRead[]>(`/providers/${code}/credentials`),
    createCredential: (code: string, data: CredentialCreate) =>
        apiClient.post<CredentialRead>(`/providers/${code}/credentials`, data),
    updateCredential: (code: string, credId: number, data: CredentialUpdate) =>
        apiClient.put<CredentialRead>(`/providers/${code}/credentials/${credId}`, data),
    deleteCredential: (code: string, credId: number) =>
        apiClient.delete<{ message: string }>(`/providers/${code}/credentials/${credId}`),

    // Models
    listModels: (code: string) => apiClient.get<ModelRead[]>(`/providers/${code}/models`),
    createModel: (code: string, data: ModelCreate) =>
        apiClient.post<ModelRead>(`/providers/${code}/models`, data),
    updateModel: (code: string, modelId: number, data: ModelUpdate) =>
        apiClient.put<ModelRead>(`/providers/${code}/models/${modelId}`, data),
    deleteModel: (code: string, modelId: number) =>
        apiClient.delete<{ message: string }>(`/providers/${code}/models/${modelId}`),
}
