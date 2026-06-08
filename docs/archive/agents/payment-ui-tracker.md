# Payment UI Agent Tracker

**Monitor:** ✅ **page_ready** — Tracks V+M+P+R+T pass (run `payment-ui-monitor-run` to re-verify)

**Prerequisite validation:** ✅ `core_ready`

**Last updated:** 2026-06-07

**Re-verify:** `paycue-db payment-ui-monitor-run`

**Requirements:** [`payment-ui-requirements.md`](payment-ui-requirements.md)

---

## Track V — Validation prerequisite

| Gate | Status |
|------|--------|
| core_ready (A+B+C) | ✅ |

## Track M — Merchant → category

| Gate | Status |
|------|--------|
| `merchant_categories.yaml` catalog | ✅ 32 merchants |
| Fuzzy long checkout URL | ✅ query-embedded domains |
| `POST /api/merchant/resolve` + candidates | ✅ |
| User confirm before recommend | ✅ modal on `/` |

## Track P — Page UX (`/`)

| Gate | Status |
|------|--------|
| Homepage payment flow | ✅ |
| URL tab + name tab | ✅ |
| Confirm merchant modal | ✅ |
| Full library rankings UI | ✅ |

## Track R — Recommend API

| Gate | Status |
|------|--------|
| `POST /api/recommend` + `merchant_id` | ✅ |
| Full library when no `card_keys` | ✅ |
| `GET /api/cards` | ✅ |

## Track T — Tests

| Gate | Status |
|------|--------|
| `tests/test_merchant_mapping.py` | ✅ |
| `tests/test_pay_web.py` | ✅ |

---

## Monitor checklist

- [x] Validation core_ready
- [x] Merchant fuzzy + confirm flow
- [x] Homepage `/` MVP
- [x] Full library recommend API
- [x] Pay test suite green
- [x] **page_ready** — `payment-ui-monitor-run` ✅
- [x] E2E smoke (long URL → confirm path → 20-card recommend) — `tests/test_payment_ui_e2e_smoke.py`

## Dev startup

```bash
bash scripts/dev_web.sh          # homepage :8000 (PYTHONPATH fixed)
bash scripts/smoke_payment_ui.sh # against running server
```

## Blockers

_(none for MVP code — run monitor for formal page_ready)_

## Post-MVP (Monitor: do not start without founder)

- Wallet filter (user's 2–3 cards)
- Category fallback when merchant unknown
- Merchant catalog → 100+ stores
