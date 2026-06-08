#!/usr/bin/env bash
# Start payment UI dev server (fixes PYTHONPATH for editable install)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=src

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# Ensure hidden .pth is readable (macOS may mark it hidden)
PTH=".venv/lib/python3.13/site-packages/_editable_impl_credit_rewards.pth"
if [[ -f "$PTH" ]]; then
  chflags nohidden "$PTH" 2>/dev/null || true
fi

echo "Starting PayCue web on http://127.0.0.1:8000"
echo "Optional CardData API: uvicorn credit_rewards.card_api.app:app --port 8080"
echo "Recommend works with SQLite fallback if :8080 is down (data/carddata.db)"
exec .venv/bin/uvicorn credit_rewards.web.app:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload \
  --reload-dir src/credit_rewards/web/static \
  --reload-dir src/credit_rewards
