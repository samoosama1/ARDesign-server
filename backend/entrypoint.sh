#!/bin/bash
set -e

python manage.py compilemessages
python manage.py migrate --noinput

exec gunicorn "$@"
