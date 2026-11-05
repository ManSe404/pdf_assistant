#!/bin/bash
# Everything CI would run: lint, format check, types, tests.
set -e
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
