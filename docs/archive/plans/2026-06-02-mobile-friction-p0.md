# Mobile Friction P0 — Implementation Plan

**Status:** Done (2026-06-02)  
**Goal:** User opens app at a store → minimal taps → card recommendation. No registration.

## P0 Checklist

- [x] **P0-1** Remove Welcome tri-choice; no wallet → card tile picker → pay (≥1 card)
- [x] **P0-2** Hide register/login UI and dev nav (Compare, Validation)
- [x] **P0-3** Default pay tab = `in_store`; persist last tab in localStorage
- [x] **P0-4** Persist last merchant (url/name) + amount; show quick "same as last" chip
- [x] **P0-5** Skip confirm modal when `confidence === 'high'` and no alt candidates
- [x] **P0-6** Primary CTA copy: 「推荐卡」; simplify confirm modal meta
- [x] **P0-7** First-time card picker uses image tiles (tap to toggle)
- [x] **P0-8** Tests pass (`test_pay_web`, `test_payment_ui_e2e_smoke`, catalog, card_image)

## Files changed

| File | Changes |
|------|---------|
| `src/credit_rewards/web/static/index.html` | Single-path UI, chip, in_store default |
| `src/credit_rewards/web/static/wallet-ui.js` | Local-only flow, memory, modal gate |
| `tests/test_pay_web.py` | HTML assertion update |
| `tests/test_payment_ui_e2e_smoke.py` | Static bundle assertion |

## localStorage keys

| Key | Purpose |
|-----|---------|
| `paycue_wallet_v1` | wallet cards |
| `paycue_card_images_v1` | image URLs |
| `paycue_pay_tab_v1` | `url` \| `name` (default `name`) |
| `paycue_last_merchant_v1` | `{ tab, merchantUrl?, merchantName?, amount }` |

## Verification (passed)

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_pay_web.py tests/test_payment_ui_e2e_smoke.py tests/test_card_catalog.py tests/test_card_image.py -q
# 23 passed
```

## Out of scope (P1)

- ~~PWA manifest + Add to Home Screen~~ ✅ (2026-06-02)
- Full English UI
- Amount-optional ranking mode

## User flow after P0

1. **First open:** 选卡 tile → 「开始用」→ 付款页（默认实体店）
2. **Return:** 直达付款页；可选「上次：Walmart · $100」chip
3. **Submit:** 高置信度 → 直接出推荐；否则简短确认框
