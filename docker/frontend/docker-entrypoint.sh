#!/bin/sh
set -eu

APP_API_BASE_URL_ESCAPED=$(printf '%s' "${APP_API_BASE_URL:-http://localhost:8000/api/v1}" | sed 's/[\\"]/\\&/g')
APP_NAME_ESCAPED=$(printf '%s' "${APP_NAME:-MyApp}" | sed 's/[\\"]/\\&/g')

cat <<EOF >/usr/share/nginx/html/runtime-config.js
window.__APP_CONFIG__ = {
  APP_API_BASE_URL: "${APP_API_BASE_URL_ESCAPED}",
  APP_NAME: "${APP_NAME_ESCAPED}",
};
EOF

exec nginx -g 'daemon off;'
