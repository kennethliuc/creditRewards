# CreditRewards — Plan

## Architecture overview

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  Mobile app     │────▶│  CreditRewards API   │────▶│  Rewards CC API     │
│  (later)        │     │  (our layer)         │     │  (upstream data)    │
└─────────────────┘     └──────────┬───────────┘     └─────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
             Card sync      Category match   Valuation engine
             (wallet)       (merchant→cat)   (cpp × multiplier)
```

**Important:** We built **our own CardData API** (`credit_rewards.card_api`) with Rewards CC–compatible routes. Data comes from **seed JSON + issuer scrape jobs**, not from copying Rewards CC’s API responses (their [terms](https://rewardscc.com/docs/) prohibit reselling/redistributing their data).

Docs: [Rewards Credit Card API](https://rewardscc.com/docs/) · [Getting Started](https://rewardscc.com/docs/getting-started/)

---

## Technical problem 1 — Latest reward rules per card

### What “fresh data” means

| Data type | Source field (Rewards CC) | Freshness concern |
|-----------|---------------------------|-------------------|
| Base earn rate | `baseSpendAmount`, `baseSpendEarnType` | Low churn |
| Category bonuses | `spendBonusCategory[]` | **High** — quarterly caps, date limits |
| Caps / limits | `isSpendLimit`, `spendLimit`, `limitEndDate` | **High** |
| Program identity | `baseSpendEarnType`, `cardKey` | Stable |
| Transfer partners | Point Transfer endpoints | Medium |

Rewards CC states data is manually reviewed from issuer sites ([docs](https://rewardscc.com/docs/)). Our job is **timely fetch + normalize**, not re-scrape issuers.

### Upstream API surface (mirror in our client)

Base host (RapidAPI): `https://rewards-credit-card-api.p.rapidapi.com`

| Our need | Rewards CC endpoint |
|----------|---------------------|
| Resolve card in user wallet | `GET /creditcard-detail-bycard/{cardKey}` |
| Search card by name | `GET /creditcard-detail-namesearch/{query}` |
| Full catalog (admin/sync) | `GET /creditcard-cardlist` |
| List spend categories | `GET /creditcard-spendbonuscategory-categorylist/` |
| Cards for a category | `GET /creditcard-spendbonuscategory-categorycard/{id}` |
| Transfer programs | `GET /creditcard-pointtransfer-transferprogramlist/` |
| Cards → partner | `GET /creditcard-pointtransfer-transferprogramcard/{id}` |
| Usage / limits | `GET /creditcard-apiusage/{skey}` |

### Our normalized model (internal)

```text
Card
  cardKey, name, issuer, program, isActive

EarnRule
  cardKey, categoryId, categoryName, multiplier
  dateLimit?, spendLimit?, resetPeriod?
  raw API payload hash + fetchedAt

ProgramValuation
  programName, cppDefault, cppCashFloor, source, updatedAt

UserWallet
  userId, cardKeys[]
```

### Sync strategy (by subscription tier)

| Plan | Caching allowed? | Strategy |
|------|------------------|----------|
| BASIC / PRO / ULTRA | **No** ([terms](https://rewardscc.com/docs/)) | Fetch **only user wallet** cards on demand; short in-memory TTL (session); monitor 429 |
| MEGA / SUPREME | Yes | Nightly sync wallet + category index; store `fetchedAt`; refresh on app open if >24h |

**MVP recommendation:** Start PRO/ULTRA for dev; budget for **MEGA** before public launch (mobile app cannot call upstream on every tap at scale).

### Phase 1 checklist — Data layer

**Card universe (Phase 1):** Top 20 general-purpose rewards cards — see [`docs/phase1-card-universe.md`](docs/phase1-card-universe.md).  
**Progress:** **20 / 20** in `data/card_registry.yaml`.

- [x] Own CardData API (Rewards CC–compatible paths) — `src/credit_rewards/card_api/`
- [x] SQLite store + seed loader — `data/seed/cards/`, `credit-rewards-db seed`
- [x] Scraper stub (issuer page fetch) — `credit-rewards-db scrape`
- [x] Typed HTTP client (local or RapidAPI fallback) — `CardDataClient`
- [x] Normalizer: API JSON → `Card` + `EarnRule[]`
- [x] Wallet service: given `cardKeys[]`, return merged rules
- [x] Category resolver v0: user picks category → `spendBonusCategoryId`
- [x] Rewards CC reference sync (registry scope only) — `credit-rewards-db sync-reference`
- [x] Expand registry to 20 cards (Wave A → B → C per phase1 doc)
- [x] Issuer parsers: `capitalone`, `discover`, `wellsfargo`, `bofa`, `apple`, `bilt`
- [ ] Rate limit handler for external RapidAPI fallback
- [x] Integration test: `amex-gold` + `Grocery Stores` returns expected multiplier

### Phase 1b — Merchant → category (needed for “at payment”)

- [x] v0: user selects from category list (no ML) — `GET /creditcard-spendbonuscategory-categorylist/`
- [x] **Visa MCC (ISO 18245) → spend category** — `data/mcc/visa_mcc_categories.yaml`, `GET /creditcard-mcc-lookup/{mcc}`, `credit-rewards-db mcc-lookup`
- [x] **v1: merchant URL / name → category** — fuzzy URL scan + user confirm modal on `/`; `POST /api/merchant/resolve`, `merchant_id` on recommend
- [ ] v2 (optional): Google Maps Spend API category from Rewards CC docs

---

## Technical problem 2 — Point / reward dollar value

Goal: compare **apples to apples** — “Card A earns $X equivalent on this $100 purchase.”

### Valuation stack (three layers)

#### Layer 1 — Floor (cash redemption)

Use when user wants conservative comparison or cash-back cards.

```text
cpp_floor = baseSpendEarnCashValue   // e.g. MR = 0.6 cpp
         OR 1.0                       // pure cash back (2% = 2 cpp on $1)
```

From API: `baseSpendEarnIsCash`, `baseSpendEarnCashValue` on card detail.

#### Layer 2 — Default program valuation (Rewards CC)

```text
cpp_default = baseSpendEarnValuation   // e.g. MR = 2.2 cpp (their subjective default)
```

Documented on card detail response ([by-card docs](https://rewardscc.com/docs/get-credit-card/card-detail/by-card)).

#### Layer 3 — User preference (our product)

```text
enum ValuationMode { CONSERVATIVE, DEFAULT, OPTIMISTIC, CUSTOM }

effective_cpp = mode == CONSERVATIVE ? cpp_floor
              : mode == DEFAULT      ? cpp_default
              : user.customCpp[program]
```

Store per user + per program; default to **CONSERVATIVE** for trust, allow power users to switch.

### Earn value formula (single purchase)

```text
purchase_amount = 100.00
multiplier      = best matching EarnRule.earnMultiplier (else baseSpendAmount)
points_earned   = purchase_amount * multiplier
dollar_value    = points_earned * (effective_cpp / 100)

# Example: $100 groceries, Amex Gold 4x MR, cpp 2.2
# points = 400, value = 400 * 0.022 = $8.80
```

### Rules engine (must handle before comparing cards)

1. **Category match** — pick highest multiplier rule where category matches and dates valid
2. **Date limits** — skip if `isDateLimit` and outside `limitBeginDate`–`limitEndDate`
3. **Spend caps** — if user tracked spend toward cap, apply reduced rate (Post-MVP: need spend tracking)
4. **Multi-category shared caps** — `spendBonusCategoryType = Multi Category` (shared pool)
5. **User-selected categories** — `Option 1` / `Option 1 (Select two)` cards need user config in wallet
6. **Cash back** — treat as `multiplier × 1 cpp` on dollar value directly

### Transfer partners (Post-MVP for recommendation)

For earn-time comparison, **Layer 1–3 on earn currency is enough**. Transfer partner optimization matters for redemption, not “which card at grocery checkout” in most cases. Defer unless comparing MR vs UR vs TYP on same purchase.

### Phase 1 checklist — Valuation

- [x] Single official CPP table (`official_cpp.yaml`, max aggregation, card overrides)
- [x] `compute_earn_value()` — one `estimated_value_usd` (no ValuationMode)
- [x] `recommendBestCard()` → sorted list + explanation string
- [x] Unit tests: cash-back, capped category, Double Cash→TYP, Amex Gold $8.80
- [ ] Show user **both** multiplier and `$X estimated value` in UI copy

---

## Current phase (Playbook)

**Idea + technical spike** — validate user problem *and* prove data/valuation pipeline works.

### This phase deliverables

1. Python (or TS) CLI/API: wallet in → category + amount in → best card out
2. No mobile app yet
3. Manual category pick is OK

### Exit criteria

- [ ] 3+ real wallet combinations tested against known-good answers (churning community benchmarks)
- [ ] Valuation mode documented; conservative matches cash-back sanity checks
- [ ] API usage within subscription limits with documented sync policy

---

## Active development — Scrape vs API comparison dashboard

**User goal:** For each Phase 1 card, scrape issuer website → store in local DB; pull Rewards CC reference (ground truth); compare; explain mismatches using issuer page evidence; show everything on a web page.

**Card scope:** Start with **5 cards already in registry** (reference JSON already synced). Expand to Top 20 per [`docs/phase1-card-universe.md`](docs/phase1-card-universe.md) in waves — do not block the dashboard on all 20 parsers.

### End-to-end flow

```text
card_registry.yaml
        │
        ├─► [A] Issuer scrape ──► SQLite (cards, spend_bonus_categories)
        │         refresh-all / refresh
        │
        ├─► [B] Rewards CC sync ──► data/reference/rewardscc/cards/*.json
        │         sync-reference (registry scope only)
        │
        └─► [C] Compare + explain ──► comparison_report.json (per card)
                    │
                    └─► [D] Web dashboard (/compare) — side-by-side UI
```

### Workstream A — Website scrape → local database

**Already built:** `credit-rewards-db refresh-all`, issuer parsers (`amex`, `chase`, `citi`), SQLite schema + CardData API.

| Task | Detail | Exit |
|------|--------|------|
| A1 | Run `refresh-all` for all registry cards; record `scraped_at` per card | 5/5 cards in DB with ≥1 earn rule each (except known edge cases) |
| A2 | Fix parser bugs found during compare (start with `amex-gold`) | Airfare 3x not 5x; no FAQ text as categories |
| A3 | Persist scrape metadata: `source_url`, `scraped_at`, optional raw HTML snapshot path under `data/scrape_snapshots/` | Audit trail for “why we parsed X” |
| A4 | Wave A registry expansion (+6 cards, same parsers) | 11 cards when Wave A complete |

**CLI:**

```bash
credit-rewards-db init && credit-rewards-db seed
credit-rewards-db refresh-all
credit-rewards-db info
```

### Workstream B — API ground truth → local reference cache

**Already built:** `sync-reference` pulls only registry cards (~15–30 API calls for 5 cards).

| Task | Detail | Exit |
|------|--------|------|
| B1 | Re-run `sync-reference` after registry changes | `data/reference/rewardscc/manifest.json` lists all registry cards |
| B2 | Add `rewards_cc_card_key` for any new cards (verify via Rewards CC name search) | Each registry row maps to upstream `cardKey` |
| B3 | Do **not** run `bulk-sync` (full catalog) | Quota stays bounded |

**CLI:**

```bash
credit-rewards-db sync-reference
# optional: --card-key amex-gold
```

### Workstream C — Compare + mismatch explanation

**Already built (partial):** `reference_validate.py` — category name match + multiplier diff + CLI `validate-reference`.

**Gaps to build:**

| Task | Detail | Output |
|------|--------|--------|
| C1 | **Normalized comparison model** — map website categories ↔ API categories (alias table, e.g. `Travel` ↔ `Airfare`, `amextravel.com`) | `src/credit_rewards/ingest/compare.py` |
| C2 | **Structured diff report** per card: `matched`, `missing_in_scrape`, `missing_in_api`, `multiplier_mismatch`, `base_rate_mismatch` | `data/reports/comparison/{card_key}.json` |
| C3 | **Root-cause notes** when mismatch: enum `scraper_bug` \| `category_mapping` \| `api_stale` \| `issuer_ambiguous` \| `cap_or_date_rule` + human-readable `explanation` citing issuer page snippet | Stored in report JSON |
| C4 | CLI `credit-rewards-db compare-all` and `compare --card-key …` | Non-zero exit if any hard mismatch |
| C5 | Optional: attach `evidence` — excerpt from last scrape snapshot or live re-fetch of issuer bullet | Links diff to source text |

**Comparison rules (v1):**

- Compare **earn multipliers** and **base earn rate** only (not benefits/credits/sign-up bonus).
- Treat match if same category after alias normalization and multiplier within ±0.01.
- Flag rotating/quarterly categories separately (Freedom Flex, Discover it) — note “activation-dependent” in explanation.

### Workstream D — Comparison web page

**New route** on existing FastAPI app (`credit_rewards.web.app`, port 8000) — separate from recommendation UI.

| Task | Detail |
|------|--------|
| D1 | `GET /compare` — HTML page listing all registry cards |
| D2 | `GET /api/compare` — JSON: all cards + scrape rules + reference rules + diff summary |
| D3 | `GET /api/compare/{card_key}` — single card detail |
| D4 | UI layout per card (expandable): **Issuer (scraped)** table \| **API (reference)** table \| **Diff** panel (green match / red mismatch / yellow mapping note) |
| D5 | Show metadata: last scraped, last reference sync, issuer URL link |
| D6 | Summary bar: N matched / N mismatched / N cards total |

**Page sections (wireframe):**

```text
┌─────────────────────────────────────────────────────────────┐
│  CreditRewards — Scrape vs API Comparison                   │
│  5 cards · 3 mismatched · Last sync: 2026-06-02           │
├─────────────────────────────────────────────────────────────┤
│ ▼ amex-gold · American Express · ⚠ 2 mismatches            │
│   ┌─ Website (scraped) ─┐  ┌─ API (reference) ─┐  ┌─ Diff ─┐
│   │ Dining    4x         │  │ Dining    4x     │  │ ✓      │
│   │ Airfare   5x        │  │ Airfare   3x     │  │ ✗ bug  │
│   │ …                   │  │ amextravel 2x    │  │ ? map  │
│   └─────────────────────┘  └──────────────────┘  └────────┘
│   Explanation: Issuer page says "3X on flights booked directly…"
└─────────────────────────────────────────────────────────────┘
```

**Tech:** Server-rendered HTML + minimal JS, or static page calling `/api/compare` — match existing `web/static/` pattern.

### Phased delivery checklist

#### Milestone M1 — 5-card pipeline (this sprint)

- [ ] A1: `refresh-all` clean run for 5 registry cards
- [ ] B1: `sync-reference` up to date
- [ ] C1–C4: compare module + `compare-all` CLI + JSON reports
- [ ] C3: root-cause explanations for known amex-gold / chase gaps
- [ ] D1–D4: `/compare` page with side-by-side tables
- [ ] Fix amex-gold parser until Airfare matches reference (proof of loop)

#### Milestone M2 — Parser quality (Wave A, +6 cards)

- [ ] Expand registry: CFU, CSR, BCP, BBP, Custom Cash, Strata Premier
- [ ] Scrape + sync + compare for 11 cards
- [ ] Category alias table covers Chase + Amex naming

#### Milestone M3 — Top 20 (Wave B/C)

- [ ] New issuers: Capital One, Discover, Wells Fargo, BofA, Apple, Bilt
- [ ] Dashboard shows all 20 with status badges (scrape ok / reference ok / aligned)

### Commands (target workflow)

```bash
# Full refresh pipeline for dashboard
credit-rewards-db refresh-all
credit-rewards-db sync-reference
credit-rewards-db compare-all          # NEW
uvicorn credit_rewards.web.app:app --host 0.0.0.0 --port 8000
# open http://127.0.0.1:8000/compare    # NEW
```

### Out of scope (this development track)

- Browser extension / autofill (Post-MVP)
- Full Top 20 before M1 dashboard ships
- Auto-fix API data (we only document discrepancies)
- Storing Rewards CC responses in production SQLite (reference JSON cache only; terms compliance)

---

## Active development — Payment UI (homepage `/`)

**Prerequisite:** Validation **`core_ready`** ✅

**User requirements:** [`docs/payment-ui-requirements.md`](docs/payment-ui-requirements.md)

**Agent system:** [`docs/payment-ui-agent-system.md`](docs/payment-ui-agent-system.md) · Tracker: [`docs/payment-ui-tracker.md`](docs/payment-ui-tracker.md)

| Track | Deliverable | Gate |
|-------|-------------|------|
| M | Merchant fuzzy URL + confirm | `payment-ui-monitor` track M |
| P | Homepage flow + modal | index.html |
| R | resolve + recommend API | `merchant_id`, full library |
| T | pytest pay suite | test_merchant_mapping, test_pay_web |

```bash
credit-rewards-db payment-ui-monitor-run
uvicorn credit_rewards.web.app:app --port 8000
# GET /api/payment-ui/monitor
```

### Phase checklist — Payment UI

- [x] Merchant → category (YAML + fuzzy URL)
- [x] User confirm merchant modal
- [x] Homepage `/` full-library ranking
- [x] Monitor `page_ready` formal sign-off + E2E smoke (`test_payment_ui_e2e_smoke.py`)
- [x] Railway deploy artifacts (`Dockerfile`, `railway.toml`, [docs/deploy-railway.md](docs/deploy-railway.md))
- [ ] Post-MVP: wallet filter, category fallback (founder approval required)

### Success criteria (this track)

| Criterion | Target |
|-----------|--------|
| Dashboard loads | All registry cards visible with both data sources |
| Transparency | Every mismatch has category + multiplier + explanation |
| Scraper loop | At least 1 card (`amex-gold`) reaches **fully matched** after parser fix |
| API quota | Reference sync stays registry-scoped (<100 calls for 5 cards) |

---

## Post-MVP roadmap

- Mobile app shell + wallet UI
- User spend cap tracking (Plaid optional)
- Personal cpp overrides
- Push: quarterly category activation reminders
- Minimum-effort / autofill (deferred)

---

## Environment

```bash
REWARDS_CC_API_KEY=          # or RapidAPI key
REWARDS_CC_BASE_URL=https://rewards-credit-card-api.p.rapidapi.com
REWARDS_CC_SKEY=             # subscription key for usage endpoint
```

Secrets on server only; mobile talks to our backend.
