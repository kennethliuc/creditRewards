# Phase 1 — Top 20 Card Universe

**Purpose:** Define which credit cards Phase 1 should support for scrape + reference sync + recommendation validation.

**Audience fit:** Multi-card holders (2–8 cards) who care about **category rewards at payment time** — aligned with [`idea.md`](../idea.md), not single-card or bad-credit segments.

**Date:** 2026-06-02

---

## Methodology

We combined four signals and filtered for **general-purpose rewards cards** (not store/secured/student-only products):

| Signal | Source | What it measures |
|--------|--------|------------------|
| **Issuer scale** | [WalletHub / Nilson Report](https://wallethub.com/edu/cc/market-share-by-credit-card-issuer/25530) | Chase (~149M cards), Capital One (~107M), Citi (~79M), Discover (~61M), BofA (~55M), Amex (~48M) dominate U.S. wallets |
| **Search / interest popularity** | [WalletHub Most Popular 2026](https://wallethub.com/most-popular-credit-cards/) | CSP, Amex Platinum, CFU, Apple Card lead general-purpose search interest |
| **Real-world “daily driver” lists** | [CreditPilot 2026 top 5 carried](https://creditpilotusa.com/most-popular-credit-cards-americans-2026/) | CFU, Discover it, Amex Gold, Cap One Venture, Citi Double Cash |
| **Optimizer wallet patterns** | r/CreditCards / r/Churning trifecta consensus | Chase (CSR/CSP + Freedom), Amex (Platinum/Gold/BBP), Citi (Premier/Custom Cash/Double Cash), Cap One (Venture X + Savor) |

**Explicitly excluded from Top 20 (Phase 2+ or out of scope):**

- Store cards (Amazon, Best Buy, Target) — merchant-specific, weak fit for generic category picker MVP
- Secured / bad-credit (Indigo, OpenSky) — not target persona in `idea.md`
- Pure 0% APR / balance-transfer cards (Wells Fargo Reflect) — no earn optimization value
- Co-brand niche (single airline/hotel) unless user promotes — Marriott/Southwest appear on WalletHub “popular” but skew travel-hobbyist

---

## Phase 1 Top 20 (recommended)

Sorted by **ecosystem importance** for multi-card optimizers, then ubiquity.

| # | card_key (proposed) | Card | Issuer | Fee | Why Phase 1 | Parser | Status |
|---|---------------------|------|--------|-----|-------------|--------|--------|
| 1 | `chase-freedom-unlimited` | Chase Freedom Unlimited | Chase | $0 | Most-carried daily driver; Chase UR pool | `chase` | **Add** |
| 2 | `chase-sapphire-preferred` | Chase Sapphire Preferred | Chase | $95 | #1 travel rewards search interest | `chase` | ✓ In registry |
| 3 | `chase-freedomflex` | Chase Freedom Flex | Chase | $0 | 5% rotating quarterly — high app value | `chase` | ✓ In registry |
| 4 | `chase-sapphire-reserve` | Chase Sapphire Reserve | Chase | $550+ | Chase trifecta premium anchor | `chase` | **Add** |
| 5 | `amex-gold` | Amex Gold | Amex | ~$325 | Dining/grocery 4x; widely held premium | `amex` | ✓ In registry |
| 6 | `amex-platinum` | Amex Platinum | Amex | ~$895 | Premium travel + MR ecosystem | `amex` | ✓ In registry |
| 7 | `citi-double-cash` | Citi Double Cash | Citi | $0 | 2% flat baseline in many wallets | `citi` | ✓ In registry |
| 8 | `capital-one-venture-x` | Capital One Venture X | Capital One | $395 | Fastest-growing premium; Reddit 2025 favorite | `capitalone` | **Add** |
| 9 | `capital-one-venture` | Capital One Venture | Capital One | $95 | Simple 2x travel; top-5 carried | `capitalone` | **Add** |
| 10 | `capital-one-savorone` | Capital One SavorOne | Capital One | $0 | Dining/entertainment 3% | `capitalone` | **Add** |
| 11 | `discover-it-cash-back` | Discover it Cash Back | Discover | $0 | 5% rotating — activation reminders = product fit | `discover` | **Add** |
| 12 | `wells-fargo-active-cash` | Wells Fargo Active Cash | Wells Fargo | $0 | 2% flat; WalletHub “best trio” staple | `wellsfargo` | **Add** |
| 13 | `amex-blue-cash-preferred` | Blue Cash Preferred | Amex | ~$95 | 6% groceries — common Amex stack | `amex` | **Add** |
| 14 | `citi-custom-cash` | Citi Custom Cash | Citi | $0 | 5% on top category — Citi trifecta | `citi` | **Add** |
| 15 | `citi-strata-premier` | Citi Strata Premier | Citi | $95 | Citi transfer partner anchor (was Premier) | `citi` | **Add** |
| 16 | `bofa-customized-cash` | Bank of America Customized Cash | BofA | $0 | 3% user-chosen category — wallet config needed | `bofa` | **Add** |
| 17 | `wells-fargo-autograph` | Wells Fargo Autograph | Wells Fargo | $0 | 3x travel/dining/streaming; no-fee multipliers | `wellsfargo` | **Add** |
| 18 | `apple-card` | Apple Card | Goldman/Apple | $0 | WalletHub top search; Apple Pay daily use | `apple` | **Add** |
| 19 | `amex-blue-business-plus` | Amex Blue Business Plus | Amex | $0 | 2x MR catch-all in Amex trifecta | `amex` | **Add** |
| 20 | `bilt-mastercard` | Bilt Mastercard | Wells Fargo | $0 | Rent + dining/travel — growing optimizer staple | `bilt` | **Add** |

**Current registry:** 5 / 20 complete.

---

## Issuer coverage (Phase 1)

| Issuer | Cards in Top 20 | New parser needed? |
|--------|-------------------|-------------------|
| Chase | 4 | No — extend `chase` parser |
| Amex | 4 | No — extend `amex` parser |
| Citi | 3 | No — extend `citi` parser |
| Capital One | 3 | **Yes** — `capitalone` |
| Wells Fargo | 3 | **Yes** — `wellsfargo` (+ `bilt` may share patterns) |
| Discover | 1 | **Yes** — `discover` |
| Bank of America | 1 | **Yes** — `bofa` |
| Apple/Goldman | 1 | **Yes** — `apple` |

---

## Implementation waves

### Wave A — Existing parsers (9 cards, ~2–3 days)

Add to `card_registry.yaml` + scrape + `sync-reference`:

- `chase-freedom-unlimited`, `chase-sapphire-reserve`
- `amex-blue-cash-preferred`, `amex-blue-business-plus`
- `citi-custom-cash`, `citi-strata-premier`

**Rewards CC sync estimate:** ~9 card details + ~30–50 category endpoints + 1 category list ≈ **40–60 API calls** (not full catalog).

### Wave B — New issuers, high wallet share (7 cards, ~1 week)

- Capital One trio (`venture-x`, `venture`, `savorone`)
- Discover it
- Wells Fargo Active Cash + Autograph

### Wave C — Wallet / config complexity (4 cards, ~1 week)

- BofA Customized Cash (user-selected 3% category)
- Apple Card (Daily Cash tiers)
- Bilt (rent category)
- Polish rotating-category UX for Freedom Flex + Discover it

---

## Validation targets (known-good scenarios)

After each wave, `validate-reference` should pass for:

| Scenario | Category | Expected winner (conservative) |
|----------|----------|------------------------------|
| $100 groceries | Grocery Stores | Amex Gold 4x or BCP 6% (cap-aware) |
| $100 dining | Dining | Amex Gold 4x or SavorOne 3% |
| $100 generic | Everything Else | Double Cash / Active Cash 2% or CFU 1.5x |
| $1,500 Q4 Freedom category | Rotating | Freedom Flex 5x (when active) |

---

## Sources

- [WalletHub — Most Popular Credit Cards 2026](https://wallethub.com/most-popular-credit-cards/)
- [WalletHub — Issuer market share](https://wallethub.com/edu/cc/market-share-by-credit-card-issuer/25530)
- [WalletHub — Most used credit cards (Nilson)](https://wallethub.com/answers/cc/most-used-credit-cards-2140830862/)
- [CreditPilot — 5 most carried 2026](https://creditpilotusa.com/most-popular-credit-cards-americans-2026/)
- [Upgraded Points — market share & popular cards](https://upgradedpoints.com/credit-cards/us-credit-card-market-share-by-network-issuer/)
- r/CreditCards trifecta consensus (Chase / Amex / Citi / Capital One)

---

## Open decision

**Honorable mentions (swap candidates if you disagree):**

- **Costco Anywhere Visa** — huge warehouse segment, but Costco-only 4% gas/warehouse
- **Wells Fargo Reflect** — popular for BT, not rewards
- **United / Delta co-brand** — common in travel wallets, defer to Phase 2

Confirm this Top 20 before we expand `card_registry.yaml` and build new issuer parsers.
