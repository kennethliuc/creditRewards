# CardData API — Rewards CC–compatible surface

Our own credit card rewards database and HTTP API. Data is curated from **issuer public pages** (same model as [Rewards CC](https://rewardscc.com/docs/)), not repackaged from their API.

## Endpoint map

| Method | Path | Source |
|--------|------|--------|
| GET | `/creditcard-cardlist` | [Card List](https://rewardscc.com/docs/get-credit-card/card-detail/card-list) |
| GET | `/creditcard-detail-bycard/{cardKey}` | [By Card](https://rewardscc.com/docs/get-credit-card/card-detail/by-card) |
| GET | `/creditcard-detail-namesearch/{name}` | [Search by Name](https://rewardscc.com/docs/get-credit-card/card-detail/search-by-name) |
| GET | `/creditcard-spendbonuscategory-categorylist/` | [Category List](https://rewardscc.com/docs/get-credit-card/spend-bonus-category/category-list) |
| GET | `/creditcard-spendbonuscategory-categorycard/{categoryId}` | [Category Card](https://rewardscc.com/docs/get-credit-card/spend-bonus-category/category-card) |
| GET | `/creditcard-pointtransfer-transferprogramlist/` | [Transfer Program List](https://rewardscc.com/docs/category/point-transfer-programs) |
| GET | `/creditcard-pointtransfer-transferprogramcard/{transferPartnerId}` | [Transfer Program Card](https://rewardscc.com/docs/category/point-transfer-programs) |
| GET | `/creditcard-mcc-lookup/{mccCode}` | Visa ISO 18245 MCC → Rewards CC spend category |
| GET | `/creditcard-valuation-programlist/` | Program official CPP (max aggregation) |
| GET | `/creditcard-valuation-bycard/{cardKey}` | Per-card valuation + example purchase dollar value |
| GET | `/creditcard-earnbonus-cards/` | [AwardWallet CC Bonus API](https://awardwallet.com/api/cc)–compatible card list |
| GET | `/creditcard-earnbonus-bycard/{cardKey}` | AwardWallet-shaped earn categories + merchants for one card |
| GET | `/creditcard-apiusage/{skey}` | [API Usage](https://rewardscc.com/docs/get-credit-card/api-usage/) |

## AwardWallet Credit Card Bonus API — comparison

Reference: [AwardWallet CC Bonus API](https://awardwallet.com/api/cc#introduction)

| Capability | AwardWallet `/v1/cards` | Our local API | Notes |
|------------|-------------------------|---------------|-------|
| Category bonuses | `earningCategories[]` | `spendBonusCategory[]` + `/creditcard-earnbonus-*` | We map 1:1; AW uses integer `categoryId`, we keep Rewards CC `spendBonusCategoryId` |
| Merchant / portal bonuses | `earningMerchants[]` + `merchantNames[]` | `/creditcard-earnbonus-*` (heuristic split) | AW lists individual merchants (e.g. streaming services); we infer portal/travel-agency rules from category text |
| Point valuation | `awardWalletPointValue` | `baseSpendEarnValuation` + `/creditcard-valuation-*` | AW = their [redemption model](https://awardwallet.com/blog/awardwallet-mile-valuations/); we use Rewards CC + Upgraded Points benchmark; optional `sync-awardwallet` adds AW value |
| Cash floor | *(not exposed)* | `baseSpendEarnCashValue` | Conservative redemption — **we have, AW lacks** |
| Short earn summary | `shortEarningDescription` | Generated on `/creditcard-earnbonus-*` | Same UX field, built from rules |
| Sign-up bonus | *(not in AW CC API)* | `signupBonus*` on card detail | **We have, AW lacks** |
| Card benefits | *(not in AW CC API)* | `benefit[]` on card detail | **We have, AW lacks** |
| Transfer partners | *(not in AW CC API)* | `/creditcard-pointtransfer-*` | **We have, AW lacks** |
| Spend caps | In HTML `description` only | `isSpendLimit`, `spendLimit`, `spendLimitResetPeriod` | Structured caps — **we have** |
| Seasonal bonuses | `startDate` / `endDate` | `limitBeginDate` / `limitEndDate` | Equivalent |
| Issuer coverage | 9 US banks | 20-card Phase 1 registry | Smaller but deeper on benefits/transfer |

Optional third valuation source:

```bash
# Requires AW commercial API credentials in .env
credit-rewards-db sync-awardwallet
curl http://127.0.0.1:8080/creditcard-earnbonus-bycard/chase-freedom-unlimited
```

Response includes `awardWalletPointValue` when cached, plus `creditRewardsExtensions` (annual fee, signup, our CPP fields).


## Point → dollar valuation

Single **official CPP** per program (`max` of Rewards CC, Upgraded Points, AwardWallet). User sees one `estimatedValueUsd` only.

| Layer | Field / source | Meaning |
|-------|----------------|---------|
| **Official table** | `data/curated/official_cpp.yaml` + `refresh-official-cpp` | Program CPP + card overrides (CFU→UR, Double Cash→TYP) |
| **Aggregation** | `max(sources)` capped at 3.5¢ | Max获得感 — one number per program |

```bash
credit-rewards-db import-reference      # also runs refresh-official-cpp
credit-rewards-db refresh-official-cpp  # recompute after sync-reference / sync-awardwallet
credit-rewards-db valuation-report
```

Formula: `dollar_value = points_earned × (official_cpp / 100)`

## Merchant → category (Visa MCC)

Visa [ISO 18245](https://usa.visa.com/dam/VCOM/download/merchants/visa-merchant-data-standards-manual.pdf) MCC codes map to Rewards CC `spendBonusCategory*` via `data/mcc/visa_mcc_categories.yaml`.

```bash
credit-rewards-db mcc-lookup 5411
curl http://127.0.0.1:8080/creditcard-mcc-lookup/5411
```

Use the returned `spendBonusCategoryName` as the `category` input to `credit-rewards recommend` or `POST /api/recommend`.


```text
Issuer website (public)
    → ingest/scrape job (manual JSON or fetch+parse)
    → SQLite (data/carddata.db)
    → CardData API (port 8080)
    → CreditRewards app / recommendation engine
```

## Coverage today vs target

| Stage | Cards | Notes |
|-------|-------|-------|
| **Now (seed)** | ~6 major US rewards cards | Enough for prototype + tests |
| **Next** | Top 50 by wallet share | Manual + scraper assists |
| **Long term** | Broad US catalog | Ongoing ops like Rewards CC |

## Run locally

```bash
credit-rewards-db init
credit-rewards-db seed
uvicorn credit_rewards.card_api.app:app --host 0.0.0.0 --port 8080
```

Set `CREDITREWARDS_DATA_API_URL=http://localhost:8080` so the app uses our API instead of RapidAPI.
