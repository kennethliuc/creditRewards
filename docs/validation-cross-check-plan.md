# Validation & Cross-Check Plan (Multi-Agent)

**Goal:** Prove the reward engine is **accurate enough** and **coverage is sufficient** before shipping payment-moment UI. This is the product core—not a nice-to-have QA pass.

**Last updated:** 2026-06-02

---

## 1. What “reliable” means (three layers)

| Layer | Question | Source of truth for MVP | Pass criterion |
|-------|----------|-------------------------|----------------|
| **L1 — Runtime data** | Do API/DB earn rules match Rewards CC reference? | `import-reference` → `carddata.db` | 20/20 cards: `validate-reference` green |
| **L2 — Ground truth** | Are reference rules still correct vs issuer + community? | Issuer pages + curated golden cases | ≥90% category rows **verified**; rest documented |
| **L3 — Product behavior** | Does `recommend` pick the right card for real wallets? | Golden wallet matrix + spot checks | ≥95% scenarios match expected winner |

**Important:** Live scrape alignment is **L2 evidence**, not L1. Runtime uses reference import; scrape/compare proves or disproves reference freshness.

---

## 2. Validation dimensions (checklist)

### A. Earn rules (multipliers, categories, caps, dates)
- Per-card `spendBonusCategory` rows vs reference
- Base earn (`baseSpendEarnType`, multiplier)
- Transfer-eligible vs cash-back labeling (affects CPP override path)
- Annual caps / quarterly rotations (flag even if out of MVP scope)

### B. Category & MCC coverage
- All Phase 1 categories in `categorylist` API
- Visa MCC → category mapping for top payment MCCs (grocery, dining, gas, travel, drugstore, etc.)
- **Gap report:** MCCs with no mapping; categories with no card in wallet

### C. Point valuation (CPP)
- `official_cpp.yaml` vs Rewards CC / Upgraded Points / optional AwardWallet
- Card overrides (CFU, Flex, Double Cash) match design spec
- Sanity cap 3.5¢; no program below 0.5¢ without explicit note

### D. Recommend ranking
- Same spend → stable ordering across CLI and `POST /api/recommend`
- Dollar value = points × official CPP (not baseSpendEarnCashValue)
- Tie-break documented (higher multiplier vs higher CPP)

### E. API surface & coverage
- 20 cards × 8 standard CardData endpoints (+ valuation, MCC, earnbonus)
- Registry completeness vs `docs/phase1-card-universe.md`

---

## 3. Multi-agent roles (parallel cross-validation)

Each agent produces **one artifact** + updates the tracker. **Monitor** merges and blocks ship.

```
                    ┌─────────────┐
                    │   Monitor   │  tracker + gates + ship/no-ship
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │ Agent Ref  │  │ Agent Issuer│  │ Agent Bench│
    │ L1 import  │  │ L2 scrape   │  │ L3 golden  │
    └────────────┘  └────────────┘  └────────────┘
           │               │               │
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │ Agent CPP  │  │ Agent MCC  │  │ Agent Rank │
    │ valuation  │  │ coverage   │  │ recommend  │
    └────────────┘  └────────────┘  └────────────┘
```

| Agent | Scope | Commands / tools | Deliverable |
|-------|-------|------------------|-------------|
| **Monitor** | Orchestration, gates, final pytest | `pytest -q`, read all reports | `docs/validation-status.md` (matrix) |
| **Reference** | L1: DB ↔ reference JSON | `sync-reference`, `import-reference`, `validate-reference` | `reports/validation/reference-{date}.json` |
| **Issuer** | L2: scrape ↔ reference + evidence | `refresh-all`, `compare-all`, `/compare` | Per-card verdict: reference_supported / scrape_supported / needs_human |
| **Benchmark** | L2: community + issuer PDFs | Manual golden sheet (see §5) | `data/validation/golden_cases.yaml` + test file |
| **CPP** | Official valuation cross-check | `refresh-official-cpp`, diff vs sources | `reports/validation/cpp-{date}.json` |
| **MCC** | Mapping coverage | `mcc-lookup` CLI + API spot checks | `reports/validation/mcc-coverage-{date}.md` |
| **Rank** | End-to-end recommend | `credit-rewards recommend`, `POST /api/recommend` | `tests/test_golden_recommend.py` (new) |

**Cross-validation rule:** No single agent owns truth. A row is **verified** only when ≥2 independent signals agree (e.g. reference + issuer evidence, or reference + golden case).

**Multi-agent orchestration:** See [`validation-agent-system.md`](validation-agent-system.md) and live tracker [`validation-agent-tracker.md`](validation-agent-tracker.md). Monitor runs `validation-independent` before assigning L2 Parser agents.

---

## 4. Phased execution

### Phase V0 — Baseline (1 session, all agents read-only)

```bash
cd creditRewards && source .venv/bin/activate
credit-rewards-db init && credit-rewards-db seed
credit-rewards-db sync-reference && credit-rewards-db import-reference
credit-rewards-db refresh-official-cpp
pytest -q
credit-rewards-db validate-reference --all    # if CLI exists; else reference_validate in tests
credit-rewards-db compare-all
```

Monitor records: pytest count, reference validate pass rate, compare aligned count (expect low on live scrape).

### Phase V1 — L1 lock (Reference agent)

**Gate:** 20/20 cards pass `validate_card_against_reference` (imported DB matches cached reference).

Actions on fail:
- Re-run `sync-reference --card-key X`
- Re-import; if reference itself wrong → escalate to Issuer + Benchmark agents

### Phase V2 — L2 earn verification (Issuer + Benchmark in parallel)

**Issuer agent** (automated + human review on `/compare`):
1. For each mismatch row, read `evidence_verdict` / `evidence_summary`
2. Classify: `reference_ok` | `reference_stale` | `scrape_parser_bug` | `ambiguous`
3. Target: **≥18/20 cards** with all high-traffic categories verified (Dining, Grocery, Travel, Gas, Other)

**Benchmark agent** (manual, high signal):
1. Build 30–50 golden rows (see §5)
2. Encode as pytest; failures = product bugs or reference bugs

**Gate:** Verified category rows / total category rows ≥ **90%** across 20 cards; every `reference_stale` has GitHub issue or curated override note.

### Phase V3 — CPP & MCC (CPP + MCC agents)

**CPP agent:**
- For each program in `official_cpp.yaml`: document source row + max() rationale
- Flag any card where recommend ranking **flips** if CPP uses conservative vs max

**MCC agent:**
- Test 25 common MCC codes (5812, 5411, 5541, 4511, 5912, …)
- Confirm mapped category returns sensible `categorycard` / recommend results

**Gate:** CPP: 100% programs have ≥1 external source; MCC: 0 unmapped codes in “top 25” list.

### Phase V4 — L3 recommend (Rank agent)

- Run golden wallet scenarios (§5) through CLI + API
- Compare vs AwardWallet earn bonus API where credentials exist (`sync-awardwallet`)

**Gate:** ≥ **95%** golden scenarios match expected card; 100% on “headline” cases (Amex Gold dining, CSR travel, CFU catch-all, Citi Double Cash everything).

### Phase V5 — Ship decision (Monitor)

| Metric | MVP ship | Post-MVP |
|--------|----------|----------|
| L1 reference import | 20/20 | maintain on sync |
| L2 verified earn rows | ≥90% | ≥98% |
| L3 golden recommend | ≥95% | ≥99% |
| Live scrape aligned | not required | ≥80% cards |
| MCC top-25 | 100% mapped | expand list |
| pytest | all green | all green |

---

## 5. Golden case matrix (Benchmark agent)

Create `data/validation/golden_cases.yaml`:

```yaml
# Example shape — expand to 30–50 cases
cases:
  - id: amex_gold_dining_100
    wallet: [amex-gold, csr, cfu]
    spend: { category: Dining, amount_usd: 100 }
    expected_winner: amex-gold
    reason: "4x MR @ 2.0cpp beats 3x UR and 1x"
  - id: csr_travel_500
    wallet: [csr, amex-gold]
    spend: { category: Travel, amount_usd: 500 }
    expected_winner: csr
  - id: mcc_grocery_5411
    wallet: [amex-gold, bilt, cfu]
    spend: { mcc: "5411", amount_usd: 80 }
    expected_winner: amex-gold  # or bilt — document assumption
```

Categories to cover at least once:
- Dining, Grocery, Travel, Airfare, Gas, Drugstore, Streaming, Transit, Hotels, Online retail, **Everything else / base earn**
- At least 3 **MCC** cases and 3 **category** cases for same merchant type (consistency check)

Optional external anchors:
- r/churning flowchart rows (document URL + date)
- Issuer benefit PDF for cap/limit edge cases

---

## 6. Artifacts & tracker

**Visualization (primary):** open **`http://127.0.0.1:8000/validation`** after `uvicorn credit_rewards.web.app:app --port 8000`.

The dashboard shows:
- Ship-ready badge + blockers
- L1 / L2 / L3 / CPP / MCC progress bars with gate thresholds
- Per-card matrix (L1 + L2 %)
- Golden recommend pass/fail table
- MCC coverage grid

Drill-down: `/compare` for issuer vs reference row-level evidence.

```
reports/validation/
  reference-YYYY-MM-DD.json
  compare-summary-YYYY-MM-DD.json
  cpp-YYYY-MM-DD.json
  mcc-coverage-YYYY-MM-DD.md
data/validation/
  golden_cases.yaml
docs/
  validation-status.md          # Monitor: single dashboard table
```

**validation-status.md** columns:

| card_key | L1 ref | L2 verified % | CPP ok | golden pass | blocker |

---

## 7. When agents disagree (tie-break)

1. **Issuer current terms** (Terms & Conditions / benefits page) beats stale reference
2. **Curated override** in repo (`data/curated/`) beats both, with citation + `effective_date`
3. **Recommend golden case** beats theoretical multiplier if user-visible outcome wrong
4. Unresolved → `needs_human` + block that card from recommend UI (fail closed for that card)

---

## 8. Coverage sufficiency (is 20 cards enough?)

Separate **accuracy** from **coverage**:

| Coverage question | How to measure | MVP answer |
|-------------------|----------------|------------|
| Wallet overlap | % of beta users’ cards in registry | Interview 5–10 users; target ≥80% |
| Spend category overlap | Golden cases cover top 80% of spend | Plaid later; use self-reported for now |
| MCC | Top 25 codes mapped | Phase V3 gate |
| Issuer diversity | Chase, Amex, Citi, Cap1, US Bank, etc. | See `phase1-card-universe.md` |

If wallet overlap <80%, expand registry—not fix parsers.

---

## 9. Automation hooks (future)

- CI job: `pytest` + `validate-reference --all` + golden recommend tests
- Weekly cron: `sync-reference` + diff alert
- Compare dashboard regression snapshot

---

## 10. Out of scope (explicit)

- Proving live scrape 100% aligned (parser maintenance is ongoing)
- Merchant-name → category (v1)
- AwardWallet as sole source of truth (commercial, optional cross-check only)
- Legal/compliance sign-off on earn claims

---

## Quick start (Monitor checklist)

- [x] V0 baseline recorded (`reports/validation/`)
- [x] Reference agent: L1 20/20
- [x] Issuer agent: compare evidence reviewed per card (`compare-summary-*.json`)
- [x] Benchmark agent: `golden_cases.yaml` (22 cases) + `tests/test_golden_recommend.py`
- [x] CPP agent: source audit (`cpp-*.json`)
- [x] MCC agent: top-24 table (`mcc-coverage-*.md`)
- [x] Rank agent: golden pass rate 100% (≥95% gate)
- [x] Ship gate documented in `validation-status.md` — **blocked on L2 parsers (11/20 scrape)**
