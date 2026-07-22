from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Mapping


POINT_TO_CNY = Decimal("0.007")
CENTS_PER_CNY = Decimal("100")


def cents_from_points(value: int | float | Decimal) -> int:
    decimal_value = Decimal(str(value))
    cents = (decimal_value * POINT_TO_CNY * CENTS_PER_CNY).quantize(
        Decimal("1"),
        rounding=ROUND_CEILING,
    )
    return max(int(cents), 0)


def pricing_cents_from_points_map(
    values: Mapping[str, int | float | Decimal],
) -> dict[str, int]:
    return {
        key: cents_from_points(value)
        for key, value in values.items()
    }


def format_cny_from_cents(amount_cents: int) -> str:
    return f"¥{Decimal(amount_cents) / CENTS_PER_CNY:.2f}"
