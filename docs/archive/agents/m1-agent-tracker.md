# M1 Agent Tracker — Scrape vs API Dashboard

**Monitor role:** Coordinator checks this file + `pytest` + `/compare` webpage after each agent completes.

**Last updated:** 2026-06-02 (20-card registry, official CPP, Visa MCC mapping)

## Milestone M1 acceptance

| # | Requirement | Owner | Status |
|---|-------------|-------|--------|
| 1 | Scrape → SQLite for 5 registry cards | Agent Scrape | ✅ |
| 2 | Reference JSON synced (`sync-reference`) | Agent Scrape | ✅ |
| 3 | `compare.py` + `compare-all` CLI + JSON reports | Agent Compare | ✅ |
| 4 | `/compare` webpage + `/api/compare` | Agent Web | ✅ |
| 5 | Parser fix: amex-gold Airfare 3x (fixture) | Agent Parser | ✅ |
| 6 | Unit tests `test_compare.py` | Agent Compare | ✅ (3 tests) |
| 7 | Web tests `test_compare_web.py` (TestClient) | Agent Web | ✅ (4 tests) |
| 8 | Full `pytest` green | Monitor | ✅ 21 passed, 1 xfailed |
| 9 | Webpage acceptance: side-by-side + diff | Monitor | ✅ API + page verified |
| 10 | Live scrape fully aligned (5/5) | Agent Parser | ⬜ use evidence column first |
| 11 | Issuer-page evidence on misaligned rows | Agent Compare | ✅ |

## Agent assignments

| Agent | Scope | Deliverables |
|-------|-------|--------------|
| **Monitor** | Progress, integration, final verification | This file, run pytest, open `/compare` |
| **Compare** | `ingest/compare.py`, CLI, unit tests | Structured diff + root-cause notes |
| **Web** | `web/static/compare.html`, API routes, web tests | Page lists all cards with both sources |
| **Parser** | `parsers.py` fixes, `test_parsers.py` | Fixture-level match; live pages next |

## Verification commands

```bash
cd creditRewards && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
paycue-db refresh-all
paycue-db compare-all
uvicorn credit_rewards.web.app:app --port 8000
# → http://127.0.0.1:8000/compare
```

## Current compare status (live scrape)

After `refresh-all` + `compare-all`: **0/5 aligned** — dashboard correctly surfaces mismatches. Next parser iteration uses `/compare` as acceptance UI.

## Blockers

_(none)_
