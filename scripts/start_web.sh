#!/usr/bin/env bash
set -euo pipefail

PERSIST_DB="${CREDITREWARDS_DB_PATH:-}"
BUILTIN_DB="/app/data/carddata.db"

if [[ -n "$PERSIST_DB" ]]; then
  mkdir -p "$(dirname "$PERSIST_DB")"
  if [[ ! -f "$PERSIST_DB" ]]; then
    echo "Seeding persistent database at $PERSIST_DB from image build..."
    cp "$BUILTIN_DB" "$PERSIST_DB"
  fi
  python -c "from credit_rewards.datastore.db import init_db; init_db()"
  paycue-db refresh-official-cpp || true
fi

PORT="${PORT:-8000}"
exec uvicorn credit_rewards.web.app:app --host 0.0.0.0 --port "$PORT"
