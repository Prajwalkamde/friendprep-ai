#!/usr/bin/env bash
set -e
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input --clear
python manage.py migrate --no-input
