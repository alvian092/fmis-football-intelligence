# FMIS Cloudflare Worker (Free-first)

This Worker replaces the Python/FastAPI hosting dependency for the FMIS dashboard. It keeps the existing frontend API contract:
- GET /api/health
- POST /api/data/csv (multipart field: file; header: X-Admin-Token)
- POST /api/analyze (JSON)

Historical matches are stored in Cloudflare Workers KV, so they survive Worker restarts. The model mirrors the repository's Poisson + Dixon-Coles calculation and explainable analyst.

## One-time Cloudflare setup

1. Create a Cloudflare account on the Free plan. Do not add a payment method or upgrade.
2. In Cloudflare Dashboard, open **Workers & Pages → KV** and create a namespace named `FMIS_DATA`.
3. Copy that namespace ID into `cloudflare/wrangler.toml`, replacing `REPLACE_WITH_CLOUDFLARE_KV_NAMESPACE_ID`.
4. In **Workers & Pages → Overview**, copy your Account ID.
5. Create a Cloudflare API token with **Edit Cloudflare Workers** permissions.
6. In the GitHub repository, open **Settings → Secrets and variables → Actions**. Add repository secrets:
   - `CLOUDFLARE_ACCOUNT_ID` = your Cloudflare Account ID
   - `CLOUDFLARE_API_TOKEN` = your API token
7. Run **Actions → Deploy FMIS Cloudflare Worker → Run workflow**.
8. After the first successful deployment, open the Worker settings and add an encrypted secret named `FMIS_ADMIN_TOKEN`. Use a long random value; do not commit or share it.
9. Copy the Worker URL (for example, `https://fmis-football-intelligence.<your-subdomain>.workers.dev`) into `frontend/config.js` as `window.FMIS_API_BASE`, without a trailing slash. Commit the change; GitHub Pages will redeploy the dashboard.

## Free-plan notes

- Cloudflare Workers Free has daily request and CPU limits. If a limit is reached, requests can fail until the quota resets; this setup does not opt into paid usage.
- Workers KV has free daily read/write limits. CSV upload uses one KV write; each analysis reads the stored dataset.
- Keep the CSV below 10 MB. The Worker validates the required columns and rejects malformed rows.
- The Worker uses a wildcard CORS response because the public GitHub Pages origin is fixed and the API has no browser cookie authentication. Protect CSV uploads with the private `FMIS_ADMIN_TOKEN`.
