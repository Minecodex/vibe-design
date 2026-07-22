import { apiClient } from '../client'

export interface HarnessBillingModelStat {
  model_name: string
  model_label: string
  calls: number
  success_calls: number
  failed_calls: number
}

export interface HarnessBillingSummary {
  mode: string
  mode_label: string
  multimodal_calls: number
  image_analysis_calls?: number
  image_generation_calls: number
  video_generation_calls: number
  multimodal_models: string[]
  image_analysis_models?: string[]
  image_models: string[]
  video_models: string[]
  multimodal_model_stats?: HarnessBillingModelStat[]
  image_analysis_model_stats?: HarnessBillingModelStat[]
  image_model_stats?: HarnessBillingModelStat[]
  video_model_stats?: HarnessBillingModelStat[]
  total_elapsed_ms: number
}

export interface HarnessUsageLogParams {
  engine?: string
  conversation_id?: string
  agent_run_id?: string
  billing_summary?: HarnessBillingSummary
  [key: string]: unknown
}

export interface UsageLogRead {
  id: number
  user_id: number
  parent_id: number | null
  nickname?: string
  avatar_url?: string
  task_id: number | null
  model_name: string
  model_label: string
  task_type: string
  amount_cents: number
  amount_cents_original: number
  status: string
  params?: HarnessUsageLogParams | Record<string, unknown> | null
  kind?: string | null
  subagent_task_id?: string | null
  subagent_label?: string | null
  billing_label: string | null
  elapsed_ms: number | null
  created_at: string
  updated_at: string
}

export interface UsageLogListRead {
  id: number
  user_id: number
  parent_id: number | null
  nickname?: string
  avatar_url?: string
  task_id: number | null
  model_name: string
  model_label: string
  task_type: string
  amount_cents: number
  amount_cents_original: number
  status: string
  kind?: string | null
  subagent_task_id?: string | null
  subagent_label?: string | null
  billing_label: string | null
  elapsed_ms: number | null
  created_at: string
  updated_at: string
}

export interface UsageLogSummaryRead {
  id: number
  engine?: string | null
  conversation_id?: string | null
  agent_run_id?: string | null
  billing_summary?: HarnessBillingSummary | null
}

export interface PaginatedUsageLogs {
  items: UsageLogRead[]
  total: number
  page: number
  page_size: number
}

export interface PaginatedUsageLogList {
  items: UsageLogListRead[]
  total: number
  page: number
  page_size: number
}

export interface BalanceRead {
  balance_cents: number
}

export const billingApi = {
  getBalance: () =>
    apiClient.get<BalanceRead>('/billing/balance'),

  getPricing: () =>
    apiClient.get<Record<string, { pricing_mode: string; prices: Record<string, number> }>>('/billing/pricing'),

  getUsageLogs: (params: {
    page?: number
    page_size?: number
    task_type?: string
    billing_label?: string
    model_name?: string
    status?: string
    task_id?: number
    user_id?: number
  }) =>
    apiClient.get<PaginatedUsageLogList>('/billing/usage', { params }),

  getUsageLogChildren: (usageLogId: number, params?: {
    page?: number
    page_size?: number
  }) =>
    apiClient.get<PaginatedUsageLogs>(`/billing/usage/${usageLogId}/children`, { params }),

  getUsageLogSummary: (usageLogId: number) =>
    apiClient.get<UsageLogSummaryRead>(`/billing/usage/${usageLogId}/summary`),

}
