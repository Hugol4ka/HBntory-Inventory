#!/bin/sh
set -e

echo "Initializing database..."
python init_db.py

echo "Starting Backoffice..."
python app.py