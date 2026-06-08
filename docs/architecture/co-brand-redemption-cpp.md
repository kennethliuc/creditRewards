# Co-brand redemption CPP — study & design

**Version:** 2026-06-02  
**Related:** [points-to-dollar-valuation-report.md](./points-to-dollar-valuation-report.md) · `data/curated/co_brand_redemption_cpp.yaml`

---

## Problem

Co-brand cards (Delta Amex, AA Citi, Hilton Amex, Starbucks Visa) earn **program-specific currency** that is mostly redeemed **at that same brand**. Our generic fallback was **1.0¢/point** for airline/hotel programs not in `official_cpp.yaml`, while Chase UR uses **2.0¢**.

That made a **2× Delta mile** purchase look like **$2.00**, same as **1× UR** — even though the user will likely spend those miles on Delta awards (~1.2¢+).

---

## Insight (user model)

| Earn context | Correct valuation lens |
|--------------|------------------------|
| Amex Gold → MR → transfer/portal | Program CPP (MR 2.2¢) |
| Delta Gold → SkyMiles @ delta.com | **Redemption at Delta** (~1.2¢/mile) |
| Hilton Surpass → Honors @ hilton.com | **Redemption at Hilton** (~0.6¢/pt) |
| Starbucks Visa → Stars @ Starbucks | **Stars at Starbucks** (~3.7¢/Star) |

Co-brand earn + co-brand spend = **closed loop**; value should not use the generic 1¢ floor.

---

## Published redemption benchmarks (study)

| Program | At-brand use case | CPP range (¢) | Source used |
|---------|-------------------|---------------|-------------|
| American AAdvantage | AA award flights | 1.4–1.6 | Upgraded Points May 2026, TPG |
| Delta SkyMiles | Delta award flights | 1.1–1.2 | Upgraded Points, TPG |
| United MileagePlus | United awards | 1.1–1.2 | Upgraded Points |
| Southwest RR | Wanna Get Away fares | ~1.4 | Industry avg |
| Alaska Atmos | Alaska awards | ~1.6 | Upgraded Points |
| JetBlue TrueBlue | JetBlue flights | ~1.3 | Points Analyst Q3 2025 |
| Marriott Bonvoy | Marriott nights | 0.7–0.9 | TPG May 2026 |
| Hilton Honors | Hilton nights | 0.4–0.6 | Upgraded Points, TPG |
| World of Hyatt | Hyatt nights | ~1.8 | Points Analyst |
| Starbucks Stars | Food/drink rewards | ~3.5 (cap) | 150 Stars ≈ $5.50 tier |

We pick **mid-conservative** values within published ranges and cap at `sanity_cap_cpp: 3.5`.

---

## Implementation (Layer B′)

When **all** of the following hold:

1. Purchase has a catalog `merchant_id` (e.g. `delta`, `american_airlines`)
2. Card `resolved_program` matches that merchant’s loyalty program
3. Entry exists in `co_brand_redemption_cpp.yaml`

Then:

```text
effective_cpp = redemption_cpp   // e.g. Delta 1.2¢, AA 1.4¢
estimated_value_usd = amount × multiplier × (effective_cpp / 100)
```

Otherwise → existing `official_cpp` / program table (UR, MR, etc.).

**Code:** `co_brand_redemption_cpp.py` · `valuation.effective_cpp_for_purchase()` · `PurchaseContext.merchant_id`

---

## Cross-validation ($100 purchase)

### Delta Gold + CSP @ delta.com

| Card | mult | CPP | $ value | Rank |
|------|------|-----|---------|------|
| Delta Gold | 2× | **1.2¢** | **$2.40** | **#1** |
| CSP | 1× | 2.0¢ | $2.00 | #2 |

### AA MileUp + CSP @ aa.com

| Card | mult | CPP | $ value | Rank |
|------|------|-----|---------|------|
| MileUp | 2× | **1.4¢** | **$2.80** | **#1** |
| CSP | 1× | 2.0¢ | $2.00 | #2 |

### AA Executive + CSR @ aa.com (premium wallet)

| Card | mult | CPP | $ value | Rank |
|------|------|-----|---------|------|
| CSR | 4× | 2.0¢ | **$8.00** | **#1** |
| AA Executive | 4× | 1.4¢ | $5.60 | #2 |

CSR still wins when user holds premium general travel cards — **correct** (4× UR @ portal value > 4× airline miles @ airline redemption).

### Starbucks Visa @ Starbucks ($100)

| Card | mult | CPP | $ value |
|------|------|-----|---------|
| Starbucks Visa | 3× Stars | 3.5¢ | **$10.50** |
| CSP (Dining 3×) | 3× UR | 2.0¢ | $6.00 |

---

## Limits & out of scope

- **No merchant_id** (OSM-only) → program CPP only; future: map co-brand category → merchant
- **Transfer/partner sweet spots** not modeled (would inflate CPP beyond sanity cap)
- **Dynamic airline pricing** — single static CPP per program; refresh quarterly with benchmarks
- **Amazon / cash-back store cards** — separate rules

---

## Maintenance

1. Update `co_brand_redemption_cpp.yaml` when Upgraded Points / TPG refresh (quarterly, same cadence as `plan.md` CPP section)
2. Add merchant row when new co-brand catalog entry ships
3. Golden tests in `tests/test_merchant_co_brand.py` lock math for AA, Delta, Starbucks
