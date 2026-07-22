from __future__ import annotations

from app.core.config import settings


def app_name_for_language(language: str | None) -> str:
    normalized = str(language or "").strip().lower()
    if normalized.startswith("zh"):
        return settings.APP_NAME
    return settings.APP_NAME_EN
