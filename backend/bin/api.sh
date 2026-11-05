#!/bin/bash
# Run the API locally with hot reload on http://127.0.0.1:8000 (docs at /api/docs).
# PORT=8010 backend/bin/api.sh picks another port.
set -e
cd "$(dirname "$0")/.."
exec uv run uvicorn pdf_assistant.api.main:create_app --factory --host 127.0.0.1 --port "${PORT:-8000}" \
    --reload --reload-dir src
