# Official CPP Valuation — Design Spec

**Date:** 2026-06-02  
**Status:** Approved  
**Product principle:** Maximize perceived reward value at payment moment (“最大获得感”)

---

## Problem

Users need **one dollar number** to compare cards at checkout—not conservative vs optimistic ranges. Multiple CPP sources (Rewards CC, Upgraded Points, AwardWallet) must collapse into a **single official cents-per-point (CPP)** per program/card.

## Decisions (locked)

| Question | Choice | Rationale (max获得感) |
|----------|--------|------------------------|
| User-facing values | **One** `estimated_value_usd` | No mode picker; reduces friction at payment moment |
| Table type | **Curated official CPP** | Auditable product table, not raw API passthrough |
| Multi-source conflict | **`max(candidates)`** | Highest defensible CPP → strongest card differentiation |
| Granularity | **Program + card overrides** | Most cards share program CPP; exceptions for pool/transfer cards |
| Cash floor in max? | **No** | Floor is minimum redemption, not a valuation candidate |
| Citi Double Cash | **Override → Citi ThankYou Rewards** | 2% earns ThankYou-eligible points when paired with Premier/Strata; value user’s transfer path |
| Chase Freedom / CFU | **Override → Chase Ultimate Rewards** | Registry UR pool; avoid 1.0¢ “Cash” API label undervaluing card |
| Sanity cap | **3.5¢ soft cap** | Only clamps obvious bad upstream data; does not bind current 20-card universe |
| Cash-back program | **Fixed 1.0 CPP** | Literal cash: `$value = amount × multiplier / 100` |

---

## User-visible formula

```text
multiplier     = best category rule (existing engine)
points_earned  = amount_usd × multiplier          # points cards
                 OR amount_usd × multiplier / 100   # treated as $ for pure cash path

official_cpp   = lookup(card_key) → program or card override → official_cpp column

estimated_value_usd = points_earned × (official_cpp / 100)   # points
                      OR amount_usd × multiplier / 100         # cash-back (1.0 cpp implicit)
```

**UI copy (example):**

> Use Amex Gold — **~$8.80** on this $100 purchase  
> 4× Grocery

No secondary “conservative” line. Optional footnote: *Estimated reward value; not guaranteed cash.*

---

## Data model

### File: `data/curated/official_cpp.yaml`

```yaml
version: "2026-06-02"
aggregation: max
sanity_cap_cpp: 3.5

programs:
  "American Express Membership Rewards":
    valuation_program_key: amex-mr
  "Chase Ultimate Rewards":
    valuation_program_key: chase-ur
  "Citi ThankYou Rewards":
    valuation_program_key: citi-typ
  "Capital One Miles":
    valuation_program_key: capone-miles
  "Bilt Points":
    valuation_program_key: bilt
  "Wells Fargo Go Far Rewards":
    valuation_program_key: wf-gofar
  "Cash":
    official_cpp: 1.0

card_overrides:
  chase-freedom-unlimited:
    use_program: "Chase Ultimate Rewards"
  chase-freedomflex:
    use_program: "Chase Ultimate Rewards"
  citi-double-cash:
    use_program: "Citi ThankYou Rewards"
  # Optional manual candidate (participates in max):
  # amex-gold:
  #   manual_cpp: 2.25
```

### SQLite: extend `program_valuations`

| Column | Purpose |
|--------|---------|
| `official_cpp` | **Single** published CPP (¢/pt) after max + cap |
| `official_cpp_updated_at` | Last refresh timestamp |
| `official_cpp_sources_json` | Internal audit: `{rewards_cc: 2.2, upgraded_points: 2.0, ...}` |

Per-card resolved CPP stored at read time: `card_official_cpp = override.use_program → program.official_cpp OR card-specific row if added later`.

---

## Max aggregation pipeline

**Command:** `credit-rewards-db refresh-official-cpp`  
**Runs after:** `sync-reference`, optional `sync-awardwallet`, `import-reference`

For each program in `official_cpp.yaml` (except fixed Cash):

```text
candidates = [
  max(baseSpendEarnValuation) across registry cards in that program,
  benchmark.cpp_default from program_benchmarks.yaml,
  max(awardWalletPointValue) across mapped cards,
  manual_cpp from YAML if present,
]
official_cpp = min(max(candidates), sanity_cap_cpp)
```

Card overrides do not compute separate CPP; they **alias** to another program’s `official_cpp`.

### Phase 1 expected official CPP (before AW sync)

| Program | RC | UP | Max → Official |
|---------|-----|-----|----------------|
| Amex MR | 2.2 | 2.0 | **2.2** |
| Chase UR | 2.0 | 2.0 | **2.0** |
| Citi TYP | 1.6 | 1.7 | **1.7** |
| Cap One Miles | 1.8 | 1.85 | **1.85** |
| Bilt | 1.0 | 2.2 | **2.2** |
| Wells Fargo Go Far | 1.0 | 1.0 | **1.0** |
| Cash | — | — | **1.0** |

---

## API & CLI changes

### User / product surface

| Endpoint / command | Change |
|--------------------|--------|
| `compute_earn_value()` | Remove `ValuationMode`; use `official_cpp` only |
| `recommend` CLI | Drop `--mode`; show single `$` |
| `GET /creditcard-valuation-bycard/{key}` | Return `officialCpp`, `estimatedValueUsd` only |
| `valuation-report` | Ops view: sources + max breakdown (not end-user) |

### Internal / debug (optional)

`GET /creditcard-valuation-debug/{key}` — lists candidates and winning max (admin only, Post-MVP).

---

## Removed / deprecated

- User-facing `ValuationMode.CONSERVATIVE | DEFAULT`
- Dual `dollarPerPoint.default` / `conservative` in valuation API responses
- Using `baseSpendEarnCashValue` as comparison CPP (keep in card detail for reference only)

---

## Testing

1. **Unit:** max aggregation with fixture sources; cap at 3.5; Cash fixed 1.0  
2. **Unit:** card override resolution (CFU → UR cpp 2.0; Double Cash → TYP 1.7)  
3. **Integration:** 20 cards — single `estimatedValueUsd` on valuation endpoint  
4. **Regression:** Amex Gold $100 grocery → **$8.80** (400 × 2.2¢)  
5. **Regression:** Citi Double Cash $100 → **$3.40** (200 pts × 1.7¢), not $2.00  

---

## Out of scope (this spec)

- Wallet-aware CPP (e.g. only value CFU as UR if user holds CSP)—Post-MVP  
- User custom CPP overrides  
- Redemption-path optimization (transfer partners at spend time)  
- Showing multiple valuations in UI  

---

## Alignment with `idea.md`

Payment-moment recommendation compares cards on **one optimistic, curated dollar value** so the “best card” answer feels meaningful and aligns with power-user mental models (transfer/portals), without asking users to pick valuation modes.
