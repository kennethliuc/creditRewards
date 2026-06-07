# Payment UI — Product Requirements (Monitor alignment)

**Owner:** Founder  
**Monitor uses this doc** to reject sub-agent work that drifts from scope.

---

## Problem & moment

User is **about to pay**. They need one answer: **which card earns the most** for this purchase, with **USD-equivalent reward value** shown clearly.

---

## MVP scope (in scope)

| # | Requirement | Status |
|---|-------------|--------|
| R1 | **Merchant → category** is mandatory before recommend | ✅ v1 |
| R2 | Checkout **URL fuzzy match** (nested URLs in Stripe/PayPal params, domain tokens in query) | ✅ |
| R2b | Unknown store/domain → **OpenStreetMap Nominatim** (free, no AI; `CREDITREWARDS_NOMINATIM=0` to disable) | ✅ |
| R3 | User **confirms merchant + category** before recommend (popup/modal) | ✅ |
| R4 | Page lives at **homepage `/`** | ✅ |
| R5 | **Full library** compare (Phase-1 registry ~20 cards), ranked by reward USD | ✅ |
| R6 | Inputs: **store URL or store name** + **amount USD** | ✅ |
| R7 | Output: **best card** + **full ranking** with estimated value + short reason | ✅ |
| R8 | Reward engine uses **validated** rules (validation `core_ready` prerequisite) | ✅ |

---

## Explicitly out of scope (Monitor blocks)

- Browser extension / checkout autofill
- Bank login / Plaid
- Wallet persistence / user accounts
- Transfer-partner redemption optimization
- Replacing manual category entirely (fallback picker is Post-MVP polish)

---

## Post-MVP (do not implement unless founder promotes)

| Item | Notes |
|------|-------|
| Wallet filter (user picks 2–3 cards) | Founder chose **full library first** |
| Manual category fallback when merchant unknown | UX polish |
| Merchant catalog expansion beyond seed YAML | MerchantAgent ongoing |
| Mobile shell | Post-MVP roadmap |

---

## Acceptance (page_ready)

Monitor marks **`page_ready`** when tracks **M + P + R + T** pass (see [`payment-ui-agent-system.md`](payment-ui-agent-system.md)) **and** validation **`core_ready`** remains true.

---

## User flow (canonical)

```
Paste checkout URL or type store name
  → POST /api/merchant/resolve
      1. YAML catalog (domain + name fuzzy in URL haystack)
      2. If no hit: Nominatim POI lookup → category via osm_category_map.yaml
  → Confirm merchant modal (always for URL; optional for exact catalog name)
  → POST /api/recommend { merchant_id, category?, merchant_name?, amount_usd }
      (osm:* ids require confirmed category from modal)
  → Show #1 card + ranked list ($USD)
```
