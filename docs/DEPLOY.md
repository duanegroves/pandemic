# Deploying to an Oracle Cloud Always Free VM

Every push to `main` runs `.github/workflows/deploy.yml`:

1. **test**: Python lint and tests, frontend tests and build.
2. **build**: builds the Docker image (`Dockerfile`: React build + Python server) for
   `linux/arm64` and pushes it to GitHub Container Registry as `ghcr.io/<owner>/<repo>:latest`
   (and `:<commit sha>`).
3. **deploy**: copies `deploy/docker-compose.yml` and `deploy/Caddyfile` to `~/pandemic` on the VM
   over SSH, then runs `docker compose pull && docker compose up -d`.

On the VM, two containers run: `app` (the game server, rooms saved in a Docker volume) and `caddy`
(reverse proxy on ports 80/443, with automatic HTTPS if you give it a domain name).

## 1. Create the VM (one time)

In the Oracle Cloud console: **Compute → Instances → Create instance**.

- **Image:** Canonical Ubuntu 24.04.
- **Shape:** Ampere `VM.Standard.A1.Flex` (Always Free eligible; 1 OCPU / 6 GB is plenty).
  If you pick the x86 `VM.Standard.E2.1.Micro` instead, set the repository variable
  `DOCKER_PLATFORMS=linux/amd64` (step 4).
- **Networking:** a public subnet, with "Assign a public IPv4 address" checked.
- **SSH keys:** upload your own public key (for you to log in).

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
| `DOCKER_PLATFORMS` | optional. `linux/amd64` for the x86 Micro shape; default is `linux/arm64`. |

Then push to `main` (or **Actions → Test, build and deploy → Run workflow**) and open
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

## Notes

- There are no accounts: anyone with the URL can create a room, and anyone with a room code can
  join an open seat. Fine for friends; don't post the URL publicly.
- Without a domain, traffic is unencrypted HTTP. Free options for a domain name include
  DuckDNS (`yourname.duckdns.org`), which works with Caddy's automatic HTTPS.
