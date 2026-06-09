#!/bin/sh
set -eu

PORT="${PORT:-5000}"
WORKERS="${WULKAN_WEB_WORKERS:-3}"
TIMEOUT="${WULKAN_GUNICORN_TIMEOUT:-60}"

if [ "${WULKAN_RUN_MIGRATIONS:-1}" = "1" ]; then
  python -m alembic upgrade head
fi

exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --timeout "${TIMEOUT}" \
  wsgi:application
