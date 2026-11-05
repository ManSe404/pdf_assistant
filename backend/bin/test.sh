#!/bin/bash
# Run the backend tests (pass pytest args through, e.g. bin/test.sh tests/test_api_chat.py -k vote).
set -e
cd "$(dirname "$0")/.."
exec uv run pytest "$@"
