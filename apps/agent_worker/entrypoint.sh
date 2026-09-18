#!/bin/sh
set -eu

codex_home="${CODEX_HOME:-/root/.codex}"
auth_file="$codex_home/auth.json"

if [ ! -s "$auth_file" ]; then
    if [ -z "${OPENAI_API_KEY:-}" ]; then
        echo "Codex authentication is missing. Mount CODEX_HOME/auth.json for local use or inject OPENAI_API_KEY from a production secret manager." >&2
        exit 1
    fi
    mkdir -p "$codex_home"
    printf '%s' "$OPENAI_API_KEY" | codex login --with-api-key
fi
echo "Running database migrations..."
cd ./infra/migrations
python -m alembic upgrade head 

exec python -m apps.agent_worker.app.main
