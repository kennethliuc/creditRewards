#!/usr/bin/env bash
# Payment UI manual smoke — Monitor Track T companion
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=src

BASE="${1:-http://127.0.0.1:8000}"
URL='https://checkout.stripe.com/pay/cs_test?return_url=https%3A%2F%2Fwww.chipotle.com%2Fdone'

echo "== Payment UI smoke ($BASE) =="

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")
[[ "$code" == "200" ]] || { echo "FAIL GET / ($code)"; exit 1; }
echo "OK GET /"

resolve=$(curl -s -X POST "$BASE/api/merchant/resolve" \
  -H 'Content-Type: application/json' \
  -d "{\"merchant_url\":\"$URL\"}")
echo "$resolve" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('best'), d
assert d['best']['merchantName']=='Chipotle', d
assert d['needsConfirmation'] is True, d
print('OK resolve →', d['best']['merchantName'], '→', d['best']['spendBonusCategoryName'])
"

mid=$(echo "$resolve" | python3 -c "import json,sys; print(json.load(sys.stdin)['best']['merchantId'])")

rec=$(curl -s -X POST "$BASE/api/recommend" \
  -H 'Content-Type: application/json' \
  -d "{\"merchant_id\":\"$mid\",\"amount_usd\":100}")
echo "$rec" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('best'), d.get('detail', d)
assert d['card_count']==20, d
assert d['resolved_category']=='Dining', d
print('OK recommend →', d['best']['card_name'], '\$'+str(d['best']['estimated_value_usd']))
"

echo "Smoke passed ✅"
