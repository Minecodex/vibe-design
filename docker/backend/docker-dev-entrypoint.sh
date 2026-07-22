#!/bin/sh
set -eu

cd /app

REQ_BASE_FILE=/app/requirements.txt
REQ_FILE=/app/requirements-dev.txt
STAMP_FILE=/usr/local/share/backend-dev-requirements.sha256

needs_install=0
needs_playwright_install=0

if ! python -c "import uvicorn" >/dev/null 2>&1; then
    needs_install=1
elif [ ! -f "$STAMP_FILE" ]; then
    needs_install=1
elif [ -f "$REQ_BASE_FILE" ] && [ -f "$REQ_FILE" ]; then
    current_hash=$(python -m runtime.dev_requirements_fingerprint "$REQ_BASE_FILE" "$REQ_FILE")
    saved_hash=$(cat "$STAMP_FILE" 2>/dev/null || true)
    if [ "$current_hash" != "$saved_hash" ]; then
        needs_install=1
    fi
fi

if ! find "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}" -path '*/chrome-linux*/chrome' -type f 2>/dev/null | grep -q .; then
    needs_playwright_install=1
fi

if [ "$needs_install" -eq 1 ]; then
    pending="$(python -m runtime.incremental_pip_sync "$REQ_BASE_FILE" "$REQ_FILE")"
    if [ -n "$pending" ]; then
        python -m pip install --disable-pip-version-check --progress-bar off \
            --index-url "${PIP_INDEX_URL:-https://pypi.org/simple}" \
            $(if [ -n "${PIP_EXTRA_INDEX_URL:-}" ]; then printf -- '--extra-index-url %s' "$PIP_EXTRA_INDEX_URL"; fi) \
            --default-timeout "${PIP_DEFAULT_TIMEOUT:-180}" \
            --retries "${PIP_RETRIES:-10}" \
            $pending
        needs_playwright_install=1
    fi
    python -m runtime.dev_requirements_fingerprint "$REQ_BASE_FILE" "$REQ_FILE" > "$STAMP_FILE"
fi

if [ "$needs_playwright_install" -eq 1 ]; then
    python -m playwright install chromium
    if [ "$(id -u)" -eq 0 ]; then
        chown -R appuser:appgroup "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}" 2>/dev/null || true
    fi
fi

exec "$@"
