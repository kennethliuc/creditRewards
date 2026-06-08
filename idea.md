# PayCue — Idea

## Problem

When someone is about to pay with a credit card, choosing the wrong card costs real money: fewer points, missed bonus categories, or suboptimal redemption value. Today, power users memorize rules or open multiple apps; everyone else defaults to one card and leaves rewards on the table.

**Testable hypothesis (draft):**

> U.S. consumers who hold **2+ rewards credit cards** and make **online or in-store card payments at least weekly** often do not use the card that maximizes rewards for that merchant/category because lookup cost (rules, caps, active offers) exceeds perceived benefit at checkout time.

## Users (initial)

| Persona | Behavior today | Pain |
|--------|----------------|------|
| **Multi-card optimizer** | 3–8 cards, tracks categories, reads r/churning | Still friction at payment moment; mental math under time pressure |
| **Casual multi-card holder** | 2–3 cards, one “daily driver” | Knows they “should” pick better card but doesn’t |
| **Not in scope (v1)** | Single card, no rewards interest | No problem to solve |

**Discovery target for interviews:** multi-card holders who’ve changed card choice at least once in the past 3 months because of rewards.

## Core flow (happy path)

**Trigger:** User is about to pay (online checkout or in-person).

```
Payment moment
    → User indicates merchant / category (or app infers it)
    → App shows: "Use [Card X]" + why (category rate, offer, cap headroom)
    → User switches to that card in Apple Wallet / physical wallet
```

### MVP focus — Reward optimization (only)

For **this** expense (merchant, category, amount):

- Recommend the **best card in the user’s wallet** for rewards value.
- Explain in one line: e.g. “5× on this category” or “~2.1¢/pt effective value for you.”
- Inputs: user’s card portfolio + card benefit rules (e.g. via Rewards CC API) + transaction context (merchant/category).

### Deferred — Minimum effort (Post-MVP)

Aggregating card details and autofill on payment surfaces (checkout autofill, extension, copy-to-clipboard flows) is **explicitly out of scope until reward recommendation is validated**. Revisit after Idea/MVP exit criteria are met.

## Value proposition (one sentence)

**At the second you pay, we tell you which card saves the most — without researching each card yourself.**

## OKR / success criteria (Idea → MVP)

### Idea stage exit (Playbook)

- [ ] Problem is **specific** (who, how often, severity) — validated in **≥8** user interviews
- [ ] Solution addresses the **problem they described**, not only our assumption
- [ ] **≥5** target users react positively to a **single-interaction prototype** (recommendation only)

### MVP north star (draft)

| Metric | Target (to refine) |
|--------|---------------------|
| Recommendation accepted | User taps “using this card” or switches to suggested card ≥40% of prompts |
| Return usage | ≥30% of users use app again within 7 days after first payment prompt |
| Time to decision | Median <10 seconds from open to chosen card |

## Differentiation (hypothesis)

- **Moment:** at payment, not monthly spend review
- **Effort:** one answer, not a dashboard to interpret
- **Personalization:** user’s actual wallet + rules, not generic “best travel card” articles

## Out of scope (explicit)

**Idea / MVP v1 — not building yet:**

- **Minimum-effort / autofill** — card detail aggregation, checkout autofill, browser extension (deferred by founder decision)
- Bank login / Plaid transaction sync as **required** for first value
- Transfer-partner optimization, manufactured spend, tax advice
- International cards / non-U.S. issuers
- Social, referrals, affiliate card applications
- “Replace Mint” — budgeting, net worth, bill pay

**Post-MVP (if validated):**

- **Minimum effort:** one-screen card details, copy-friendly fields, Safari/Chrome extension or iOS autofill for supported merchants
- Receipt/merchant detection (location, paste URL, share extension)
- Notifications for category caps and quarterly activations

## Open questions (customer discovery)

1. Is the pain **at checkout** or mostly **after the fact** (regret / spreadsheet)?
2. How do users describe merchant/category today (manual pick, search, GPS)?
3. Is a clear **“use this card”** recommendation enough, or do they need more before switching cards?
4. Would they trust a third-party app with card metadata (product names, last 4) without storing PAN/CVV?

## Playbook stage

**Current stage:** Idea — **build-first prototype** (user choice: ship then iterate).

**Deliverable:** web + CLI recommendation for one core interaction.

**Still recommended in parallel:** show prototype to 5 users and note where they hesitate.

**Next gate:** iterate from usage feedback → MVP scope (mobile shell, saved wallet).
