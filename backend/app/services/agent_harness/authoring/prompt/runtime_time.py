from __future__ import annotations

from datetime import UTC, datetime

from app.core.datetime_utils import get_app_timezone


def runtime_time_payload() -> dict[str, str]:
    utc_now = datetime.now(UTC).replace(microsecond=0)
    local_tz = get_app_timezone()
    local_now = utc_now.astimezone(local_tz)
    return {
        "current_date": local_now.date().isoformat(),
        "current_local_time": local_now.isoformat(),
        "current_utc_time": utc_now.isoformat(),
        "timezone": local_tz.key,
    }


def runtime_time_block(language: str) -> str:
    payload = runtime_time_payload()
    if str(language or "").lower().startswith("zh"):
        return (
            "Current runtime time:\n"
            f"- 当前日期: {payload['current_date']}\n"
            f"- 当前本地时间: {payload['current_local_time']}\n"
            f"- 当前 UTC 时间: {payload['current_utc_time']}\n"
            f"- 当前时区: {payload['timezone']}"
        )
    return (
        "Current runtime time:\n"
        f"- Current date: {payload['current_date']}\n"
        f"- Current local time: {payload['current_local_time']}\n"
        f"- Current UTC time: {payload['current_utc_time']}\n"
        f"- Timezone: {payload['timezone']}"
    )
