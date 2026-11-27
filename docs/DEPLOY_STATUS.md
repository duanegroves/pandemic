# Deployment status

Status as of 2026-11-26. How the options fit together: [DEPLOY.md](DEPLOY.md).

| Target | Status |
|---|---|
| Cloudflare Worker (`cloudflare/worker/`, [CLOUDFLARE.md](CLOUDFLARE.md)) | **Live** at the account's `workers.dev` URL (`https://pandemic-game.<subdomain>.workers.dev`), from a manual deploy of the code at commit `d3abe1d`. Later changes (limits, eviction, idle cleanup) are not deployed yet: redeploy by hand. |
| CI auto-deploy to Cloudflare | Not enabled. Needs the repository secret `CLOUDFLARE_API_TOKEN` (and `CLOUDFLARE_ACCOUNT_ID`) and the variable `CLOUDFLARE_ENABLED=true`. |
| Oracle VM with the Docker image ([DEPLOY_ORACLE.md](DEPLOY_ORACLE.md)) | Not provisioned (Ampere A1 creation hit "Out of capacity"). The `build` job already pushes images to ghcr.io; the `deploy` job is skipped until the VM exists and `DEPLOY_ENABLED=true`. |

## Remaining steps

- Cloudflare: see "Deploy by hand" and "Deploy via GitHub Actions" in [CLOUDFLARE.md](CLOUDFLARE.md).
- Oracle: create the VM and follow [DEPLOY_ORACLE.md](DEPLOY_ORACLE.md) (the troubleshooting
  table is at its end).
