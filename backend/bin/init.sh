#!/bin/bash
# Create or upgrade the database (SQLite in backend/data by default). Safe to run again.
set -e
cd "$(dirname "$0")/.."
exec uv run alembic upgrade head
