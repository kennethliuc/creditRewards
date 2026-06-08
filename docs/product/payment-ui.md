# Payment UI — Product Spec

**Status:** Shipped (web + PWA + Railway) · **Last updated:** 2026-06-02  
**Live:** https://paycue-production.up.railway.app

---

## Problem & moment

User is **about to pay** (online checkout or in-store). They need one answer: **which card earns the most** for this purchase, with **USD-equivalent reward value** shown clearly.

---

## MVP requirements

| # | Requirement | Status |
|---|-------------|--------|
| R1 | **Merchant → category** resolved before recommend | ✅ |
| R2 | Checkout **URL** fuzzy match (Stripe/PayPal embedded URLs) | ✅ |
| R2b | **Website tab** → catalog + URL parse; **no Google Maps POI** | ✅ |
| R2c | **In-store tab** → catalog name, then **Google Places** (+ GPS); Nominatim fallback | ✅ |
| R3 | User **confirms** merchant + category when confidence is not high | ✅ |
| R4 | Homepage at **`/`** | ✅ |
| R5 | Compare **user wallet only**, ranked by reward USD | ✅ |
| R6 | Inputs: **URL or store name** + **optional amount** (defaults $100) | ✅ |
| R7 | Output: **best card** + full ranking + short reason | ✅ |
| R8 | Engine uses **validated** rules (`core_ready` gates) | ✅ |
| R9 | **PWA**: manifest, icons, Add to Home Screen hint | ✅ |

---

## Purchase channel (核心规则)

**Channel before POI.** Same brand often maps to different bonus categories online vs in-store.

| UI tab | User intent | `purchase_channel` | Resolver |
|--------|-------------|-------------------|----------|
| **网站** | Paste checkout / store URL | `online` | Domain → catalog → `web:{domain}`; default Online Shopping |
| **实体店** | Type store name | `in_store` | Catalog name → Google Places (+ GPS) → Nominatim fallback |

**Rules:**

- Website tab: **no GPS**, **no Google Maps POI**.
- In-store tab: GPS optional but recommended; Google Maps matches nearby POI.
- `gmaps:*` IDs are **in_store only**; `web:*` IDs are **online only**.

### API

```json
POST /api/merchant/resolve
{ "merchant_url": "https://www.nike.com/checkout", "purchase_channel": "online" }

POST /api/merchant/resolve
{ "merchant_name": "Nike", "latitude": 30.27, "longitude": -97.74, "purchase_channel": "in_store" }
```

Omitted `purchase_channel`: URL → `online`, name → `in_store`.

### Category mapping (catalog)

Dual categories in `merchant_categories.yaml`:

| channel | Field used |
|---------|------------|
| `online` | `online_category` ?? `spend_bonus_category_name` |
| `in_store` | `in_store_category` ?? `spend_bonus_category_name` |

### Acceptance examples

| Brand | Input | Expected category |
|-------|-------|-------------------|
| Nike | `nike.com` (website) | Online Shopping |
| Nike | store name + GPS (in-store) | All Purchases |
| Walmart | `walmart.com` | Online Shopping |
| Walmart | store name + GPS | Grocery Stores |
| Chipotle | either channel | Dining |
| Unknown URL | website tab | Online Shopping (low confidence → confirm) |

---

## User flow

```
Language (first visit) → Pick cards (local wallet) → Pay
  → Tab: 网站 | 实体店
  → POST /api/merchant/resolve
  → Confirm modal (skipped when high-confidence single catalog match)
  → POST /api/recommend
  → Best card + ranking
```

**Wallet:** Local-only MVP (no login). Data in `localStorage` on device. Manage via nav **Wallet · N cards**.

**Account mode** (email/password, SQLite wallet) is implemented in API but **not exposed in UI** — see [archive/specs/2026-06-07-wallet-onboarding-design.md](../archive/specs/2026-06-07-wallet-onboarding-design.md).

### localStorage keys

| Key | Purpose |
|-----|---------|
| `paycue_wallet_v1` | Wallet cards |
| `paycue_lang_v1` | Locale |
| `paycue_pay_tab_v1` | Last tab (`url` \| `name`) |
| `paycue_last_merchant_v1` | Last merchant + amount |
| `paycue_savings_v1` | Saved reward lookups |
| `paycue_install_dismiss_v1` | PWA install banner dismissed |

---

## Out of scope (do not implement unless promoted)

- Browser extension / checkout autofill
- Bank login / Plaid
- Transfer-partner redemption optimization
- LLM merchant/category guessing
- Using Google Maps **store POI** to infer **online** Online Shopping

## Post-MVP

- Account UI (register/login)
- Manual category picker when unknown
- Merchant catalog expansion
- Native iOS shell (TestFlight) — see plan.md Post-MVP
- Phase B: audit Top merchants for dual categories; automated § acceptance tests

---

## Verification

```bash
pytest tests/test_pay_web.py tests/test_payment_ui_e2e_smoke.py tests/test_google_places.py -q
curl -sS https://paycue-production.up.railway.app/api/health
```

Prerequisite: validation **`core_ready`** — see [validation/status.md](../validation/status.md).
