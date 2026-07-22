from __future__ import annotations

from fastapi import HTTPException, status

from app.core.money import format_cny_from_cents


INSUFFICIENT_BALANCE_CODE = "INSUFFICIENT_BALANCE"


def insufficient_balance_detail(
    *,
    required_cents: int,
    balance_cents: int | None = None,
) -> dict[str, int | str]:
    detail: dict[str, int | str] = {
        "code": INSUFFICIENT_BALANCE_CODE,
        "message": f"余额不足，需要 {format_cny_from_cents(required_cents)}",
        "required_cents": required_cents,
    }
    if balance_cents is not None:
        detail["balance_cents"] = balance_cents
    return detail


def raise_insufficient_balance(
    *,
    required_cents: int,
    balance_cents: int | None = None,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=insufficient_balance_detail(
            required_cents=required_cents,
            balance_cents=balance_cents,
        ),
    )
