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
Set `FMIS_ADMIN_TOKEN` on the backend host. Deploy backend with `render.yaml`; deploy `frontend/` using GitHub Pages Actions and set `FMIS_API_BASE` in `frontend/config.js` to the backend URL. CSV data is currently in memory and will be lost on restart; persistent storage is a future milestone.

**Android APK is not yet available:** the native Android Gradle project and wrapper have not been added. The APK workflow remains a manual guard until then.

Probabilities are estimates, not guarantees. The analyst is deterministic and explainable; no automated wagering functionality is included.
