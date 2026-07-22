#!/bin/sh
set -eu

cd /app

LOCK_FILE=/app/package-lock.json
STAMP_FILE=/app/node_modules/.package-lock.sha256

needs_install=0

if [ ! -d /app/node_modules ]; then
    needs_install=1
elif [ ! -f "$STAMP_FILE" ]; then
    needs_install=1
elif [ -f "$LOCK_FILE" ]; then
    current_hash=$(sha256sum "$LOCK_FILE" | awk '{print $1}')
    saved_hash=$(cat "$STAMP_FILE" 2>/dev/null || true)
    if [ "$current_hash" != "$saved_hash" ]; then
        needs_install=1
    fi
fi

if [ "$needs_install" -eq 1 ]; then
    npm install --registry=https://registry.npmmirror.com
    sha256sum "$LOCK_FILE" | awk '{print $1}' > "$STAMP_FILE"
fi

exec "$@"
