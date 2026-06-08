# Points → Dollar Valuation — Design Report & Proof

**Version:** 2026-06-07 (Round 1)  
**Audience:** Product, engineering, independent reviewers  
**Related:** [official-cpp-valuation.md](./official-cpp-valuation.md) · [valuation-multi-agent-system.md](../validation/valuation-multi-agent-system.md)

---

## 1. Executive summary

PayCue shows **one number** at checkout: `estimated_value_usd` (“≈ $X reward value”). Users compare cards on that `$`, not on raw points.

**Core formula (points cards):**

```text
points_earned       = purchase_amount_usd × earn_multiplier
official_cpp        = cents per point (¢/pt) from curated table
estimated_value_usd = points_earned × (official_cpp / 100)
```

**Example — Amex Gold, $100 at grocery, 4× MR, CPP 2.2¢:**

```text
points = 100 × 4 = 400 MR
value  = 400 × 0.022 = $8.80
```

**Production check (2026-06-07):** Amex Gold @ Starbucks $25 (Dining 4×) → 100 pts, **$2.20**, `cpp_used: 2.2` ✓

### Why “6 points = $6” feels wrong

Common confusion sources:

| Symptom | Likely cause | Correct interpretation |
|---------|--------------|------------------------|
| See **6** next to **$6** | **Cash-back card** on ~$100 purchase at **6%** | Field `points_earned` is misnamed for cash; value is **6% of $100 = $6**, not “6 MR points” |
| **6 MR points** valued at **$6** | Bug: `official_cpp` missing → fallback `cpp_default` wrong, or points treated as **dollars** | Should be 6 × 0.022 = **$0.13** at 2.2¢ (Amex MR) |
| Rankings differ only by **multiplier** | Amount left blank → app uses **$100 estimate** | UI note: “Est. based on $100” (`pay.amountEstimateNote`) |

**Product follow-up (Round 2):** Rename `points_earned` → `reward_units` in API/UI for cash cards; show “6% cash back ($6)” vs “400 pts (~$8.80)”.

---

## 2. Estimation method (three layers)

### Layer A — Earn (how many points)

| Input | Source |
|-------|--------|
| Merchant → category | `merchant_categories.yaml`, MCC, resolve API |
| Category → multiplier | Card `spendBonusCategory` rules + caps/dates |
| Base earn | `baseSpendAmount` if no bonus matches |

Engine: `best_multiplier()` in `valuation.py`.

**Not in scope at checkout:** spend-cap exhaustion, user-selected rotating categories (Phase 2).

### Layer B — Official CPP (how much each point is worth)

Single **official** CPP per reward program (not user-selectable conservative/optimistic).

**Pipeline:**

```text
candidates = [
  max(baseSpendEarnValuation) from Rewards CC registry cards in program,
  upgraded_points benchmark (program_benchmarks.yaml),
  max(AwardWallet) when synced,
  manual_cpp from official_cpp.yaml if set,
]
official_cpp = min(max(candidates), sanity_cap_cpp=3.5)
```

**Card overrides** (alias only — same CPP as program):

| Card | Maps to program | Why |
|------|-----------------|-----|
| Chase Freedom / CFU | Chase Ultimate Rewards | Points pool as UR when paired |
| Citi Double Cash | Citi ThankYou Rewards | 2% → TY-eligible with Premier/Strata |

**Cash program:** fixed **1.0¢** — literal cash back:

```text
estimated_value_usd = amount × multiplier / 100
```

### Layer C — Display

- **Hero:** `estimated_value_usd` only (i18n `result.value`)
- **Meta:** purchase amount + category + multiplier reason
- **Ranking:** sorted by `estimated_value_usd` DESC
- **Internal audit:** `cpp_used` on each ranking row (API)

---

## 3. Official CPP table (Phase 1)

| Program | Official CPP | Primary redemption proof |
|---------|-------------|---------------------------|
| **American Express Membership Rewards** | **2.2¢** | Portal ~2¢ travel; transfers 1.6–2¢+; floor **0.6¢** cash-out |
| **Chase Ultimate Rewards** | **2.0¢** | Chase travel portal ~1.5–2¢; transfers ~2¢; floor **1.0¢** cash/statement |
| **Citi ThankYou Rewards** | **1.7¢** | Citi portal; transfers ~1.6–1.8¢; floor **0.8¢** |
| **Capital One Miles** | **1.85¢** | Travel erasure ~1¢; transfer partners up to ~1.85¢ cited |
| **Bilt Points** | **2.2¢** | Bilt travel 2.2¢; Hyatt transfer up to ~2.2¢; rent 1¢ |
| **Wells Fargo Go Far Rewards** | **1.0¢** | Primarily cash/travel at ~1¢ |
| **Cash** | **1.0¢** | 1% back = 1¢ per $1 spent |

Sources aggregated in DB: `program_valuations.official_cpp_sources_json` after `paycue-db refresh-official-cpp`.

---

## 4. Redemption proof (why we believe each CPP)

### 4.1 American Express Membership Rewards — 2.2¢

| Redemption path | Typical ¢/pt | Evidence |
|-----------------|-------------|----------|
| **Floor — cover charges** | **0.6¢** | Amex “Pay with Points” / statement credit for charges |
| **Amex Travel portal** | ~2.0¢ | Redeem MR for flights/hotels via Amex Travel |
| **Transfer partners** | 1.6–2.0¢+ | e.g. ANA, Aer Lingus sweet spots; varies |
| **Rewards CC default** | 2.2¢ | `baseSpendEarnValuation` on Amex Gold card detail |
| **Upgraded Points benchmark** | 2.0¢ | `program_benchmarks.yaml` |

**Why official = 2.2¢ (max):** Highest **published, defensible** benchmark among RC + UP; aligns with premium travel portal redemption without assuming unicorn transfers.

**Hand check:** 400 MR × 2.2¢ = **$8.80** on $100 × 4× grocery.

### 4.2 Chase Ultimate Rewards — 2.0¢

| Path | ¢/pt | Evidence |
|------|------|----------|
| Floor | 1.0¢ | Cash/statement/gift cards |
| Chase Travel (Sapphire) | ~1.5–2.0¢ | UR portal with CSP/CSR |
| Transfers | ~2.0¢ | Hyatt, United at ~2¢ cited |
| RC / UP | 2.0¢ | Registry + benchmarks |

**CFU/ Freedom override:** Earn 1:1 UR pool → use UR CPP, not 1.0¢ “Cash” label from API.

### 4.3 Citi ThankYou Rewards — 1.7¢

| Path | ¢/pt |
|------|------|
| Floor | 0.8¢ |
| Portal / transfers | ~1.6–1.8¢ |
| **Double Cash path** | 2% earn → TY points @ 1.7¢ → **$3.40** on $100 (not $2.00) |

### 4.4 Capital One Miles — 1.85¢

Travel erasure baseline ~1¢; partner transfers (e.g. Avianca) cited up to ~1.85¢ — official uses max defensible published benchmark.

### 4.5 Bilt Points — 2.2¢

Bilt travel portal **2.2¢** documented; competes with Hyatt transfer value — max = 2.2¢.

### 4.6 Cash — 1.0¢

Not points economics:

```text
$100 × 2% cashback → $2.00 reward (not “200 points”)
```

---

## 5. Worked examples (registry cards)

| Scenario | Calculation | `$` shown |
|----------|-------------|-----------|
| Amex Gold, $100 grocery, 4× | 400 × 2.2¢ | **$8.80** |
| Amex Gold, $25 Starbucks dining, 4× | 100 × 2.2¢ | **$2.20** |
| Chase Sapphire Preferred, $100 travel, 5× | 500 × 2.0¢ | **$10.00** |
| Citi Double Cash, $100 anything, 2% | 200 TY × 1.7¢ | **$3.40** |
| Wells Fargo Active Cash, $100, 2% | 2% cash path | **$2.00** |
| Discover it, $100, 5% rotating | 5% cash on $100 | **$5.00** (`points_earned` field shows 5) |

---

## 6. Implementation map

| Step | Code | Risk |
|------|------|------|
| Load card rules | `normalize_card_detail`, category snapshots | Wrong multiplier |
| Attach CPP | `_enrich_wallet` → `resolve_card_official_cpp` | Catalog card missing program → undervalued as Cash |
| Compute $ | `compute_earn_value` | Cash vs points branch |
| Rank | `recommend_best_cards` | Sort key correct |
| UI | `wallet-ui.js` `bestValue`, `rank-usd` | Must use `estimated_value_usd` only |

**Critical:** `effective_cpp()` uses `official_cpp` when > 0; else falls back to `cpp_default` from Rewards CC. Catalog cards **must** go through `_enrich_wallet`.

---

## 7. Independent verification (Round 1 results)

Run: `python scripts/valuation_verify.py`

| Program | Official | RC max | UP bench | Floor | Verdict |
|---------|----------|--------|----------|-------|---------|
| Amex MR | 2.2 | 2.2 | 2.0 | 0.6 | ✅ max(2.2,2.0) ≤ 3.5 |
| Chase UR | 2.0 | 2.0 | 2.0 | 1.0 | ✅ |
| Citi TYP | 1.7 | 1.6 | 1.7 | 0.8 | ✅ |
| Cap One | 1.85 | 1.8 | 1.85 | 0.5 | ✅ |
| Bilt | 2.2 | 1.0* | 2.2 | 1.0 | ✅ max picks 2.2 |
| WF Go Far | 1.0 | 1.0 | 1.0 | 1.0 | ✅ |
| Cash | 1.0 | fixed | fixed | 1.0 | ✅ |

\*Bilt RC registry card may show 1.0 until refresh; benchmark + portal justify 2.2.

**Golden tests:** `test_amex_gold_grocery_dollar_value` → $8.80 ✅

**IndependentVerifier challenge (Round 1):**

1. **Using max CPP** overstates value for users who only cash out at floor — **accepted product tradeoff** (see idea.md “最大获得感”); document in UI footnote Post-MVP.
2. **`points_earned` naming** on cash-back cards — **accepted bug** for Round 2 UX fix.
3. **Transfer unicorn redemptions** not required for CPP — we cap at 3.5¢ to avoid TPG fantasy values.

**Round 1 status:** `valuation_ready: true` for registry + official CPP pipeline; **Round 2** for UX clarity + catalog-card program resolution audit.

---

## 8. Iteration roadmap

| Round | Focus | Owner agent |
|-------|-------|-------------|
| **1** ✅ | Methodology doc + evidence table + verify script | All |
| **2** ✅ | UI: separate cash vs points display; footnote modal | Designer + Impl |
| **3** ✅ | Catalog card program resolution audit script + normalize | Impl + Independent |
| **4** | Optional conservative CPP mode | Designer (Post-MVP) |

---

## 9. How to re-verify

```bash
# Refresh CPP from sources
paycue-db refresh-official-cpp

# Automated multi-agent verification
python scripts/valuation_verify.py

# Golden unit tests
pytest tests/test_valuation_twenty_cards.py tests/test_official_cpp.py -q

# Production spot-check
curl -sS -X POST https://paycue-production.up.railway.app/api/recommend \
  -H 'Content-Type: application/json' \
  -d '{"merchant_id":"starbucks","amount_usd":100,"card_keys":["amex-gold"]}'
# Expect: points_earned=400, estimated_value_usd=8.8, cpp_used=2.2
```

---

## 10. References

- Internal: `data/curated/official_cpp.yaml`, `data/reference/program_benchmarks.yaml`
- Rewards CC: `baseSpendEarnValuation`, `baseSpendEarnCashValue` on card detail
- Upgraded Points valuations (2026-06-02 snapshot in repo)
- Issuer portals: Amex Travel, Chase UR portal, Citi ThankYou portal (manual spot checks)
