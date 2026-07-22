from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.billing import (
    BalanceRead,
    PaginatedUsageLogList,
    PaginatedUsageLogs,
    UsageLogListRead,
    UsageLogRead,
    UsageLogSummaryRead,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/balance", response_model=BalanceRead)
async def get_balance(db: DbSession, user: CurrentUser):
    svc = BillingService(db)
    balance_cents = await svc.get_display_balance(user.id)
    return BalanceRead(balance_cents=balance_cents)


@router.get("/pricing")
async def get_pricing():
    return BillingService.get_pricing_rules()


@router.get("/usage", response_model=PaginatedUsageLogList)
async def list_usage_logs(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    task_type: str | None = None,
    billing_label: str | None = None,
    model_name: str | None = None,
    status: str | None = None,
    task_id: int | None = None,
    user_id: int | None = None,
):
    svc = BillingService(db)

    if user.role == "admin" and user_id is not None:
        query_user_id = user_id if user_id > 0 else None
    elif user.role == "admin" and user_id is None:
        query_user_id = None
    else:
        query_user_id = user.id

    items, total = await svc.get_usage_logs(
        user_id=query_user_id,
        task_type=task_type,
        billing_label=billing_label,
        model_name=model_name,
        log_status=status,
        task_id=task_id,
        top_level_only=True,
        page=page,
        page_size=page_size,
        include_params=False,
    )
    return PaginatedUsageLogList(
        items=[UsageLogListRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/usage/{usage_log_id}/summary", response_model=UsageLogSummaryRead)
async def get_usage_log_summary(
    usage_log_id: int,
    db: DbSession,
    user: CurrentUser,
):
    svc = BillingService(db)
    parent_log = await svc.usage_repo.get(usage_log_id)
    if not parent_log:
        raise HTTPException(status_code=404, detail="用量记录不存在")
    if user.role != "admin" and parent_log.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该用量记录")

    summary = await svc.get_usage_log_summary(usage_log_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="用量记录不存在")
    return UsageLogSummaryRead.model_validate(summary)


@router.get("/usage/{usage_log_id}/children", response_model=PaginatedUsageLogs)
async def list_usage_log_children(
    usage_log_id: int,
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    svc = BillingService(db)
    parent_log = await svc.usage_repo.get(usage_log_id)
    if not parent_log:
        raise HTTPException(status_code=404, detail="用量记录不存在")
    if user.role != "admin" and parent_log.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该用量记录")

    scoped_user_id = None if user.role == "admin" else user.id
    items, total = await svc.get_usage_log_children(
        usage_log_id,
        user_id=scoped_user_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedUsageLogs(
        items=[UsageLogRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
