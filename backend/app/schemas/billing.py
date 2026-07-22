from datetime import datetime

from pydantic import BaseModel


class HarnessBillingModelStatRead(BaseModel):
    model_name: str
    model_label: str
    calls: int
    success_calls: int
    failed_calls: int


class HarnessBillingSummaryRead(BaseModel):
    mode: str
    mode_label: str
    multimodal_calls: int
    image_analysis_calls: int | None = None
    image_generation_calls: int
    video_generation_calls: int
    multimodal_models: list[str]
    image_analysis_models: list[str] | None = None
    image_models: list[str]
    video_models: list[str]
    multimodal_model_stats: list[HarnessBillingModelStatRead] | None = None
    image_analysis_model_stats: list[HarnessBillingModelStatRead] | None = None
    image_model_stats: list[HarnessBillingModelStatRead] | None = None
    video_model_stats: list[HarnessBillingModelStatRead] | None = None
    total_elapsed_ms: int


class UsageLogRead(BaseModel):
    id: int
    user_id: int
    parent_id: int | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    task_id: int | None = None
    model_name: str
    model_label: str
    task_type: str
    amount_cents: int
    amount_cents_original: int
    kind: str | None = None
    subagent_task_id: str | None = None
    subagent_label: str | None = None
    billing_label: str | None = None
    elapsed_ms: int | None = None
    status: str
    provider_code: str | None = None
    provider_request_id: str | None = None
    provider_trace_id: str | None = None
    provider_task_id: str | None = None
    billing_mode: str | None = None
    billing_attempt_count: int = 0
    billing_next_run_at: datetime | None = None
    billing_locked_until: datetime | None = None
    billing_finalized_at: datetime | None = None
    provider_quota: int | None = None
    provider_prompt_tokens: int | None = None
    provider_completion_tokens: int | None = None
    params: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BalanceRead(BaseModel):
    balance_cents: int


class UsageLogListRead(BaseModel):
    id: int
    user_id: int
    parent_id: int | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    task_id: int | None = None
    model_name: str
    model_label: str
    task_type: str
    amount_cents: int
    amount_cents_original: int
    kind: str | None = None
    subagent_task_id: str | None = None
    subagent_label: str | None = None
    billing_label: str | None = None
    elapsed_ms: int | None = None
    status: str
    provider_code: str | None = None
    provider_request_id: str | None = None
    provider_trace_id: str | None = None
    provider_task_id: str | None = None
    billing_mode: str | None = None
    billing_attempt_count: int = 0
    billing_next_run_at: datetime | None = None
    billing_locked_until: datetime | None = None
    billing_finalized_at: datetime | None = None
    provider_quota: int | None = None
    provider_prompt_tokens: int | None = None
    provider_completion_tokens: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UsageLogSummaryRead(BaseModel):
    id: int
    engine: str | None = None
    conversation_id: str | None = None
    agent_run_id: str | None = None
    billing_summary: HarnessBillingSummaryRead | None = None


class PaginatedUsageLogs(BaseModel):
    items: list[UsageLogRead]
    total: int
    page: int
    page_size: int


class PaginatedUsageLogList(BaseModel):
    items: list[UsageLogListRead]
    total: int
    page: int
    page_size: int
