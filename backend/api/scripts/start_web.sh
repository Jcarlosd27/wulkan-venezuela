#!/bin/sh
set -eu

PORT="${PORT:-5000}"
WORKERS="${FVENTAS_WEB_WORKERS:-1}"
THREADS="${FVENTAS_WEB_THREADS:-4}"
TIMEOUT="${FVENTAS_GUNICORN_TIMEOUT:-60}"
MAX_REQUESTS="${FVENTAS_GUNICORN_MAX_REQUESTS:-600}"
MAX_REQUESTS_JITTER="${FVENTAS_GUNICORN_MAX_REQUESTS_JITTER:-60}"

if [ "${FVENTAS_RUN_MIGRATIONS:-1}" = "1" ]; then
  python -m alembic upgrade head
fi

python scripts/harden_production_defaults.py

exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --threads "${THREADS}" \
  --timeout "${TIMEOUT}" \
  --max-requests "${MAX_REQUESTS}" \
  --max-requests-jitter "${MAX_REQUESTS_JITTER}" \
  wsgi:application
