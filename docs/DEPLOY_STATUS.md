# Deployment status and handoff

Status as of 2026-11-27. **If you are an agent picking up "finish the deployment", start here.**
Overview of the options: `docs/DEPLOY.md`.

There are two independent deploy targets:

| Target | Status |
|---|---|
| Cloudflare Worker + Durable Objects (`cloudflare/worker/`, `docs/CLOUDFLARE.md`) | Code and tests done (conformance suite passes against `pywrangler dev`; `pywrangler deploy --dry-run` builds). **Not deployed yet**: the user will deploy by hand after review. Replaces the spike at https://pandemic-game.duanegroves.workers.dev. CI job `deploy-cloudflare` is skipped until `CLOUDFLARE_ENABLED=true` plus the secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` exist. |
| Oracle VM with the Docker image (below, `docs/DEPLOY_ORACLE.md`) | Blocked on the VM; see below. |

## Cloudflare: remaining steps

1. `cd web && npm ci && npm run build`, then `cd ../cloudflare/worker && ./scripts/sync.sh`.
2. `uv run pywrangler deploy` (needs uv >= 0.13.4, and `pywrangler login` or the two env vars).
3. Verify: `uv run --all-extras python tests/conformance/conformance.py --base https://pandemic-game.<subdomain>.workers.dev`
   and play a game in a browser. Watch CPU time with `uv run pywrangler tail` (or `npx wrangler tail`).
4. For CI: create the API token, `gh secret set CLOUDFLARE_API_TOKEN`, `gh secret set
   CLOUDFLARE_ACCOUNT_ID`, `gh variable set CLOUDFLARE_ENABLED --body true`.

## Oracle VM (Docker image)

## Done

- Public repo: https://github.com/duanegroves/pandemic (branch `main`).
- `Dockerfile` (React build + Python server, multi-arch `linux/amd64,linux/arm64`), tested
  locally: the image builds, and the exact `deploy/docker-compose.yml` stack (app + Caddy) served
  the site and played full games over WebSockets; rooms persisted across restarts.
- `.github/workflows/deploy.yml`: `test` and `build` jobs pass; images are pushed to
  `ghcr.io/duanegroves/pandemic:latest` and `:<sha>`.
- The `deploy` job is **skipped** until the repo variable `DEPLOY_ENABLED=true` is set. It has
  never run yet.
- Full human guide: `docs/DEPLOY_ORACLE.md`.

## Blocked on

The user creating the Oracle Cloud VM. Ampere A1 creation failed with "Out of capacity"; see the
troubleshooting section in `docs/DEPLOY_ORACLE.md`. Either shape (A1 arm64 or E2.1.Micro x86) works
with the current image.

## Remaining steps (for the agent)

Ask the user for: the VM's **public IP**, the **SSH username** (`ubuntu` on Ubuntu images,
`opc` on Oracle Linux), and an optional **domain name**. Confirm with the user that they have
done the VM-side setup in `docs/DEPLOY_ORACLE.md` sections 1 ("Open ports 80 and 443": both the
Security List and iptables) and "Install Docker". If the user can SSH in from this machine, you
can check those yourself (`ssh <user>@<ip> 'docker compose version; sudo iptables -L INPUT -n'`).

1. **Deploy key** (on the user's machine, only if it doesn't exist yet):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/pandemic_deploy -N "" -C "github-actions-deploy"
   cat ~/.ssh/pandemic_deploy.pub
   ```
   The user (or you, if their own SSH access works) appends the `.pub` line to
   `~/.ssh/authorized_keys` on the VM. Verify:
   `ssh -i ~/.ssh/pandemic_deploy -o StrictHostKeyChecking=accept-new <user>@<ip> 'echo ok'`.
   Never print or paste the private key; pipe it straight into `gh secret set`.

2. **Secrets and variables** (run in the repo root; `gh` is installed and authenticated):
   ```bash
   gh secret set OCI_HOST --body "<ip>"
   gh secret set OCI_USER --body "<user>"
   gh secret set OCI_SSH_KEY < ~/.ssh/pandemic_deploy
   gh variable set DEPLOY_ENABLED --body true
   # optional, only if the user has a domain whose A record points at the VM:
   gh variable set SITE_ADDRESS --body "<domain>"
   ```

3. **Deploy and watch:**
   ```bash
   gh workflow run deploy.yml --ref main
   sleep 5; gh run watch "$(gh run list --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
   ```

4. **Verify:** `curl -s -o /dev/null -w '%{http_code}\n' http://<ip>/` should print `200`, and
   `curl -s http://<ip>/meta | head -c 80` should show JSON city data. Then run a scripted game
   against it: `cd web && node scripts/play.mjs --base http://<ip> --games 1`. Optionally open
   the site in a browser and create a room.

5. Update this file's status section, commit, and push.

## Likely problems

| Symptom | Cause / fix |
|---|---|
| `curl` times out | Port 80 blocked: Security List ingress rule or iptables on the VM (Oracle Ubuntu images reject by default). |
| deploy job: `ssh: handshake failed` / `unable to authenticate` | Public key not in `~/.ssh/authorized_keys` for `OCI_USER`, or the wrong username. |
| deploy job: `permission denied ... docker.sock` | User isn't in the `docker` group: `sudo usermod -aG docker <user>`, then reconnect. |
| deploy job: `docker compose: unknown command` | Install `docker-compose-v2` (Ubuntu) or the compose plugin. |
| `exec format error` in `docker compose logs app` | Image/CPU mismatch; check `DOCKER_PLATFORMS` isn't set to the wrong arch. |
| HTTPS doesn't work with a domain | DNS A record not pointing at the VM yet, or port 443 not open. Caddy logs: `docker compose logs caddy`. |

## Not done / ideas

- GitHub warns that some workflow actions target Node.js 20; harmless for now, bump action
  versions later.
- No accounts: anyone with the URL can create or join rooms.
