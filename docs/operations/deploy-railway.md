# Deploy to Railway

**Live demo:** https://paycue-production.up.railway.app

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
   | `CREDITREWARDS_USER_AGENT` | `PayCue/0.1 (demo; contact: YOUR_EMAIL)` |
   | `CREDITREWARDS_USE_LOCAL_API` | `false` |
   | `CREDITREWARDS_FETCH_EVIDENCE` | `0` |
   | `CREDITREWARDS_NOMINATIM` | `1` |
   | `CREDITREWARDS_ANALYTICS_ADMIN_PASSWORD` | *(trial)* Strong password for `/admin` usage dashboard |
   | `CREDITREWARDS_ANALYTICS_ENABLED` | `1` (default) — set `0` to disable client event collection |

   **No RapidAPI / Rewards CC key is required.** The Docker build runs `import-reference` + `import-catalog-wallet` from committed `data/reference/` (~527 wallet catalog cards).

   Optional: `CREDITREWARDS_USE_UPSTREAM_API=1` + `REWARDS_CC_API_KEY` only for one-off reference backfill (`scripts/backfill_catalog_reference.py`), not runtime.

   Do **not** commit the API key to git. Railway injects `PORT` and `RAILWAY_GIT_COMMIT_SHA` automatically.

5. **Persistent SQLite (analytics + runtime data)** — attach a [Railway Volume](https://docs.railway.com/reference/volumes) so redeploys do not wipe trial analytics:

   ```bash
   railway volume add --mount-path /data
   railway variable set CREDITREWARDS_DB_PATH=/data/carddata.db
   ```

   On first boot the container copies the image-built `carddata.db` onto the volume; later deploys keep the same file. `scripts/start_web.sh` runs migrations before serving.

6. **Settings → Networking → Generate Domain** → you get `https://….up.railway.app`.
7. Share that URL; homepage is `/`.

## Trial analytics (beta testers)

When users open the app, anonymous events are batched to `POST /api/analytics/events` (device id in browser `localStorage`, no PII).

- **Admin dashboard:** `https://YOUR_DOMAIN.up.railway.app/admin` — sign in with `CREDITREWARDS_ANALYTICS_ADMIN_PASSWORD`.
- **Tracked events:** `app_open`, `app_close`, `screen_view`, `setup_complete`, `wallet_save`, `merchant_resolve`, `recommend`, `language_pick`, etc.
- **Disable collection:** `CREDITREWARDS_ANALYTICS_ENABLED=0`.

Analytics tables live in the same SQLite file as card data. With `CREDITREWARDS_DB_PATH=/data/carddata.db` on a Railway Volume, analytics survive redeploys.

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
