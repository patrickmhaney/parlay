#!/usr/bin/env bash
# Dev entrypoint. Production runs through docker-compose (see README).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1
