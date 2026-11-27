# Deploying the Docker image to an Oracle Cloud Always Free VM

Part of the deployment options in `docs/DEPLOY.md`. The Cloudflare option is in `docs/CLOUDFLARE.md`.

The CI jobs that build the image and deploy it are described in [DEPLOY.md](DEPLOY.md#cicd)
(`.github/workflows/ci.yml`): `build` pushes a multi-arch image (`linux/amd64`, `linux/arm64`) to
`ghcr.io/<owner>/<repo>`, and `deploy` copies `deploy/docker-compose.yml` and `deploy/Caddyfile` to
`~/pandemic` on the VM over SSH, then runs `docker compose pull && docker compose up -d`.

On the VM, two containers run: `app` (the game server, rooms saved in a Docker volume) and `caddy`
(reverse proxy on ports 80/443, with automatic HTTPS if you give it a domain name).

## 1. Create the VM (one time)

In the Oracle Cloud console: **Compute → Instances → Create instance**.

- **Image:** Canonical Ubuntu 24.04.
- **Shape:** Ampere `VM.Standard.A1.Flex` (Always Free eligible; 1 OCPU / 6 GB is plenty), or the
  x86 `VM.Standard.E2.1.Micro` (1 GB RAM, also enough for this server). The image is built for
  both CPU types, so no settings change between them.
- **Networking:** a public subnet, with "Assign a public IPv4 address" checked.
- **SSH keys:** upload your own public key (for you to log in).

### "Out of capacity for shape VM.Standard.A1.Flex"

Free Ampere capacity is often exhausted in popular regions. Options, roughly in order:

1. **Try the other availability domains** (AD-2, AD-3) in the Placement section, if your region
   has them. Don't pick a fault domain.
2. **Ask for less:** 1 OCPU / 6 GB instead of the 4 / 24 maximum.
3. **Retry later.** Capacity frees up unpredictably; early morning in the region's time zone often
   works. People also script retries with the OCI CLI (`oci compute instance launch` in a loop).
4. **Use the x86 `VM.Standard.E2.1.Micro`** shape instead (Always Free, usually available).
   1 GB RAM is enough for this server; no repo changes are needed.
5. **Upgrade the account to Pay As You Go.** Always Free resources stay free, and PAYG accounts
   get priority for A1 capacity. Set a budget alert in case anything non-free is created.

### Open ports 80 and 443

Two firewalls need opening:

1. **Oracle's network firewall:** Instance → subnet → its Security List → **Add Ingress Rules**:
   source `0.0.0.0/0`, TCP, destination port `80`; and again for `443`.
2. **The VM's own iptables** (Oracle's Ubuntu images block everything except SSH). SSH in and run:

   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

### Install Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu     # then log out and back in
mkdir -p ~/pandemic
docker compose version             # check it works
```

## 2. A deploy key for GitHub Actions

On your own machine, create a key used only by the workflow:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pandemic_deploy -N "" -C "github-actions-deploy"
```

Append `~/.ssh/pandemic_deploy.pub` to `~/.ssh/authorized_keys` on the VM (as the `ubuntu` user).
Test it: `ssh -i ~/.ssh/pandemic_deploy ubuntu@<VM_IP>`.

## 3. Repository secrets

GitHub repo → **Settings → Secrets and variables → Actions → Secrets** (or `gh secret set`):

| Secret | Value |
|---|---|
| `OCI_HOST` | the VM's public IP |
| `OCI_USER` | `ubuntu` |
| `OCI_SSH_KEY` | the contents of `~/.ssh/pandemic_deploy` (the **private** key) |

```bash
gh secret set OCI_HOST --body "<VM_IP>"
gh secret set OCI_USER --body "ubuntu"
gh secret set OCI_SSH_KEY < ~/.ssh/pandemic_deploy
```

## 4. Repository variables

**Settings → Secrets and variables → Actions → Variables** (or `gh variable set`):

| Variable | Value |
|---|---|
| `DEPLOY_ENABLED` | `true`. The deploy job is skipped until this is set, so pushes before the VM is ready still test and build. |
| `SITE_ADDRESS` | optional. A domain name pointing at the VM (an `A` record to its IP), e.g. `pandemic.example.com`, for automatic HTTPS. Leave unset to serve plain HTTP at `http://<VM_IP>/`. |
| `DOCKER_PLATFORMS` | optional. Default `linux/amd64,linux/arm64`; set one to speed up builds. |

Then push to `main` (or **Actions → CI → Run workflow**) and open
`http://<VM_IP>/` (or `https://<your domain>/`).

## Operating it

```bash
ssh ubuntu@<VM_IP>
cd ~/pandemic
docker compose ps                 # status
docker compose logs -f app        # server logs
docker compose restart app
```

- Rooms are saved to the `pandemic-data` volume and reloaded when the server restarts, so a
  deploy doesn't end games in progress (players' browsers reconnect automatically).
- Roll back to an earlier commit's image: `TAG=<commit sha> docker compose up -d` (you may need to
  `docker login ghcr.io` first, since the image is private). The next push deploys `latest` again.
- The image is private by default (it inherits the repo's visibility). The deploy job logs the VM
  in with a short-lived token for each pull, so nothing long-lived is stored on the VM.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `curl` times out | Port 80 blocked: Security List ingress rule or iptables on the VM (Oracle Ubuntu images reject by default). |
| deploy job: `ssh: handshake failed` / `unable to authenticate` | Public key not in `~/.ssh/authorized_keys` for `OCI_USER`, or the wrong username. |
| deploy job: `permission denied ... docker.sock` | User isn't in the `docker` group: `sudo usermod -aG docker <user>`, then reconnect. |
| deploy job: `docker compose: unknown command` | Install `docker-compose-v2` (Ubuntu) or the compose plugin. |
| `exec format error` in `docker compose logs app` | Image/CPU mismatch; check `DOCKER_PLATFORMS` isn't set to the wrong arch. |
| HTTPS doesn't work with a domain | DNS A record not pointing at the VM yet, or port 443 not open. Caddy logs: `docker compose logs caddy`. |

After the first deploy, check `curl -s -o /dev/null -w '%{http_code}\n' http://<VM_IP>/` (expect
`200`) and `curl -s http://<VM_IP>/meta | head -c 80`, then run a scripted game:
`cd web && node scripts/play.mjs --base http://<VM_IP> --games 1`.

## Notes

- The server limits (room cap, idle eviction, message sizes) and the no-accounts model are
  described in [DEPLOY.md](DEPLOY.md#limits-and-housekeeping-both-backends). Don't post the URL
  publicly.
- Without a domain, traffic is unencrypted HTTP. Free options for a domain name include
  DuckDNS (`yourname.duckdns.org`), which works with Caddy's automatic HTTPS.
