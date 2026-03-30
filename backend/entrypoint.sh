#!/bin/bash
set -e

python manage.py collectstatic --noinput
python manage.py compilemessages
python manage.py migrate --noinput

exec gunicorn "$@"
