# Deploy to Railway

**Live demo:** https://credit-rewards-production.up.railway.app

Public demo URL for the payment homepage (`/`).

## What gets deployed

- **One Docker container**: FastAPI web app + SQLite `carddata.db` (built from `data/reference/` at image build time)
- **Card art**: `data/card_images/` (bundled PNG/JPG for Phase-1 registry — no Rewards CC key needed for images)
- **No** separate CardData API on `:8080`
- **No** Rewards CC API key required at runtime

## One-time setup

1. Push this repo to GitHub (if not already).
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → select `creditRewards`.
3. Railway detects `Dockerfile` / `railway.toml` automatically.
4. **Variables** (Project → Service → Variables):

   | Variable | Value |
   |----------|--------|
   | `CREDITREWARDS_USER_AGENT` | `CreditRewards/0.1 (demo; contact: YOUR_EMAIL)` |
   | `CREDITREWARDS_USE_LOCAL_API` | `false` |
   | `CREDITREWARDS_FETCH_EVIDENCE` | `0` |
   | `CREDITREWARDS_NOMINATIM` | `1` |
   | `REWARDS_CC_API_KEY` | *(recommended)* Your Rewards CC API key — enables recommend for all ~527 wallet catalog cards not pre-imported at build |

   Without `REWARDS_CC_API_KEY`, registry (20) + category-snapshot cards (~380) work; remaining catalog cards fail recommend until the key is set.

   Do **not** commit the API key to git. Railway injects `PORT` and `RAILWAY_GIT_COMMIT_SHA` automatically.

5. **Settings → Networking → Generate Domain** → you get `https://….up.railway.app`.
6. Share that URL; homepage is `/`.

## Verify

```bash
curl -sS "https://YOUR_DOMAIN.up.railway.app/api/health"
curl -sS -X POST "https://YOUR_DOMAIN.up.railway.app/api/merchant/resolve" \
  -H "Content-Type: application/json" \
  -d '{"merchant_name":"Chipotle"}'
```

## Redeploy

Push to the connected branch; Railway rebuilds the image (runs `import-reference` again).

## Cost

Railway hobby usage is typically ~**$5/month** after trial credits. See [railway.app/pricing](https://railway.app/pricing).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Build fails on `import-reference` | Ensure `data/reference/rewardscc/cards/*.json` is committed |
| 502 on cold start | Wait for health check; first deploy can take 2–3 min |
| Unknown store slow | Nominatim is rate-limited (1 req/s); normal for demo |
| Compare page slow | Set `CREDITREWARDS_FETCH_EVIDENCE=0` (already default in Dockerfile) |
