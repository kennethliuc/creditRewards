# CreditRewards

Payment-moment credit card recommendation + **own CardData API** (Rewards CC–compatible).

## Data philosophy

**Card rewards are scraped from issuer websites — not manually maintained.**

- `data/card_registry.yaml` — cardKey + issuer URL only (no reward numbers)
- `credit-rewards-db refresh-all` — fetches live pages and parses earn rules
- Issuer parsers: `amex`, `chase`, `citi` (extend in `src/credit_rewards/ingest/scrape/`)

## Quick start

```bash
cd creditRewards
source .venv/bin/activate
pip install -e ".[dev]"

# 1) DB + category taxonomy
credit-rewards-db init
credit-rewards-db seed

# 2) Scrape rewards from issuer sites (required before API has card data)
credit-rewards-db refresh-all

# 3) CardData API (:8080)
uvicorn credit_rewards.card_api.app:app --host 0.0.0.0 --port 8080

# 4) Recommend app (:8000)
cp .env.example .env
uvicorn credit_rewards.web.app:app --host 0.0.0.0 --port 8000
```

## Scrape commands

```bash
# All cards in registry
credit-rewards-db refresh-all

# One card
credit-rewards-db refresh --card-key amex-gold

# Ad-hoc URL test
credit-rewards-db scrape --card-key my-card --url https://... --parser chase
```

## Add a new card

1. Add entry to `data/card_registry.yaml` (url + parser)
2. Run `credit-rewards-db refresh --card-key ...`
3. If parser fails, add/improve issuer rules in `ingest/scrape/parsers.py`

## API examples

See [docs/architecture/api-spec.md](docs/architecture/api-spec.md) and [Rewards CC docs](https://rewardscc.com/docs/getting-started/).

```bash
curl http://127.0.0.1:8080/creditcard-detail-bycard/amex-gold
curl http://127.0.0.1:8080/creditcard-apiusage/dev
```

## Rewards CC reference (validation only)

Use upstream API as **golden data** to tune scrapers — not as your runtime data source.

```bash
# Pull only cards in data/card_registry.yaml (~64 API calls for 20 cards, NOT the full catalog)
credit-rewards-db sync-reference

# Load Rewards CC JSON into local CardData API (aligned multipliers for all 20 cards)
credit-rewards-db import-reference

# Point/mile → dollar value (CPP from Rewards CC + Upgraded Points benchmark cross-check)
credit-rewards-db valuation-report

# One card
credit-rewards-db sync-reference --card-key amex-gold

# Compare scraped DB vs reference (CLI + JSON reports)
credit-rewards-db compare-all

# Web dashboard — side-by-side scrape vs API
uvicorn credit_rewards.web.app:app --host 0.0.0.0 --port 8000
# → http://127.0.0.1:8000/compare

# Validation dashboard (L1–L3 + CPP + MCC gates)
uvicorn credit_rewards.web.app:app --port 8000
# → http://127.0.0.1:8000/validation

# Full validation run (writes reports/validation + docs/validation/status.md)
credit-rewards-db validation-report

# Phase 1 only — Monitor gate (L1 + L3 + CPP + MCC, no scrape)
credit-rewards-db validation-independent

# Monitor: JSON task plan for fixer agents
credit-rewards-db validation-monitor
# credit-rewards-db validation-monitor --include-l2   # after Phase 1
```

Set `REWARDS_CC_API_KEY` in `.env` (RapidAPI). Do **not** run `bulk-sync` unless you explicitly want every US card (~50k calls).

Validation gates: [`docs/validation/status.md`](docs/validation/status.md).

## Tests

```bash
pytest
pytest tests/test_card_api_twenty_cards.py  # all 8 CardData endpoints × 20 registry cards
pytest tests/test_valuation_twenty_cards.py  # point CPP + dollar value × 20 cards
```

Parser unit tests use HTML snippets; integration tests use scraped-shaped fixtures (no live network in CI).

## Deploy (Railway)

Share the payment demo at a public HTTPS URL:

1. See **[docs/operations/deploy-railway.md](docs/operations/deploy-railway.md)** for step-by-step setup.
2. Railway builds `Dockerfile` (SQLite from `data/reference/`, no API keys at runtime).
3. Set `CREDITREWARDS_USER_AGENT` with your contact email for Nominatim.

```bash
# Optional: local smoke (after pip install -e .)
PORT=8000 bash scripts/start_web.sh
```

## Docs

Index: **[docs/README.md](docs/README.md)**

- [`idea.md`](idea.md) — product vision & OKR
- [`plan.md`](plan.md) — architecture & phased checklist
- [`docs/product/payment-ui.md`](docs/product/payment-ui.md) — payment homepage spec
- [`docs/operations/deploy-railway.md`](docs/operations/deploy-railway.md) — public demo deploy
