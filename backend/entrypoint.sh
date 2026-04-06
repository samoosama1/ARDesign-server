#!/bin/bash
set -e

python manage.py collectstatic --noinput
python manage.py compilemessages

if [ "${RUN_MIGRATIONS}" = "true" ]; then
  echo "Running migrations..."
  python manage.py migrate --noinput
else
  echo "Skipping migrations (RUN_MIGRATIONS != true)"
fi

exec gunicorn "$@"
