# FMIS — Football Match Intelligence System

CSV-first football probability analytics for research and education. Estimates 1X2, totals and Asian Handicap outcomes using Poisson with Dixon-Coles low-score adjustment.

## Features
- Admin-token protected CSV upload and validation
- Match probabilities and quarter-line full/half/push settlement buckets
- Explainable deterministic Match Analyst (not a generative AI)
- FastAPI backend, static web dashboard, tests and GitHub Actions CI

## CSV
Required: `date,home_team,away_team,home_goals,away_goals`. Optional: `competition,home_xg,away_xg`. Use ISO dates.

## Run
```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
python -m pytest -q
```
Dashboard: http://127.0.0.1:8000 · API docs: http://127.0.0.1:8000/docs

## Deploy

### Cloudflare Worker + persistent KV (recommended)
1. In Cloudflare, confirm the KV namespace ID in `cloudflare/wrangler.toml` exists in the same account.
2. From the `cloudflare/` directory, install Wrangler if needed and run `npx wrangler login`.
3. Set the upload secret: `npx wrangler secret put FMIS_ADMIN_TOKEN`.
4. Deploy: `npx wrangler deploy`.
5. Copy the exact Worker URL shown by Wrangler/Cloudflare.
6. Put that URL (without a trailing slash) in `frontend/config.js` as `window.FMIS_API_BASE`.
7. Deploy the `frontend/` directory using GitHub Pages Actions.

The Worker stores the complete dataset and its metadata together in the Cloudflare KV key `dataset:v1`. The `GET /api/health` and `GET /api/data/info` endpoints report the loaded row count and last save time. Re-uploading replaces the active dataset. Cloudflare KV is persistent, but propagation to other locations can be eventually consistent; verify the saved row count after upload before relying on the dataset. The previous `matches` KV key is still readable as a legacy fallback.

### FastAPI alternative
Set `FMIS_ADMIN_TOKEN` on the backend host and deploy with `render.yaml`. The current FastAPI implementation stores uploaded CSV data in process memory, so it is not restart-persistent. Use Cloudflare Worker + KV when persistent storage is required.

**Android APK is not yet available:** the native Android Gradle project and wrapper have not been added. The APK workflow remains a manual guard until then.

Probabilities are estimates, not guarantees. The analyst is deterministic and explainable; no automated wagering functionality is included.
