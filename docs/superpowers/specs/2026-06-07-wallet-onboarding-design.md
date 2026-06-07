# Wallet onboarding — Local + Account modes

**Date:** 2026-06-07  
**Status:** Approved (founder: cardKey sync + nickname + last4 for accounts)

## Summary

Two entry paths on first visit; shared payment flow afterward; manage-wallet for add/remove.

| Mode | Auth | Storage | Card fields |
|------|------|---------|-------------|
| Local | None | `localStorage` | `card_key`, optional `nickname`, `last4` |
| Account | Email + password | SQLite `user_wallet_cards` | `card_key`, `nickname`, `last4` |

Recommend ranks **wallet cards only** (not full 20-card library).

## Screens

1. **Welcome** — Local vs Register vs Login
2. **Local setup** — multi-select registry cards
3. **Register** — credentials + card picker + nickname/last4 per card
4. **Login** — email/password → pay if wallet exists else setup
5. **Pay** — current URL/name flow + wallet bar + manage link
6. **Manage wallet** — add/remove/edit nickname/last4; logout (account) or reset (local)

## API

- `POST /api/auth/register` — `{ email, password, cards: [{ card_key, nickname?, last4? }] }`
- `POST /api/auth/login` — session cookie
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/wallet` — account session only
- `PUT /api/wallet` — replace cards list

## Out of scope

- PAN / CVV storage
- Custom multipliers
- Plaid / issuer login
