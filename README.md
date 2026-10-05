# Homelab-IaC

Infrastructure-as-Code for my homelab. Every service runs as a Docker Compose stack, deployed and managed via GitOps rather than by hand through a web UI, by [Komodo](https://github.com/moghtech/komodo). Komodo pulls each compose file directly from this repo and redeploys a stack within 5 minutes of a commit that changes it. There's no build system, CI pipeline, or test suite; a compose file in this repo *is* the deployment.

## Layout

```
stacks/
  nelson-nuc/   # Intel NUC, primary host — most services live here
  quark-vm/     # Proxmox VM (Tailscale IP 100.76.105.3) — paperless, crashplan, dozzle-agent
  kirks-bar/    # OptiPlex 7040 + Quadro P1000 (192.168.88.23, Tailscale IP 100.110.243.115), GPU host — jellyfin, dozzle-agent
```

Each subdirectory under `stacks/<host>/` is one GitOps stack: a `docker-compose.yml`, plus (where needed) a `.env-example` and/or `secrets/*-example` file documenting what real values are expected. Actual secrets and `.env` files are never committed — they live directly on the host at an absolute path the compose file references. Every stack is deployed by Komodo.

## What runs manually

A few things are always bootstrapped by hand, not by GitOps, since they're prerequisites for GitOps itself:
- **Komodo Core, its Mongo database, and the Periphery agent on each host** — deployed at `/home/nelson/containers/komodo/` on nelson-nuc, deliberately kept outside this repo, since it's what deploys the repo. Periphery is what actually executes `docker compose` on each host on Komodo's behalf. kirks-bar (192.168.88.23, Ubuntu 26.04) runs a standalone Periphery as `kirk`, deployed by the [ansible repo](https://github.com/nph4/homelab-ansible)'s `komodo-periphery.yml` rather than by hand. Core's port is bound to nelson-nuc's LAN IP (`192.168.88.101:9120`), and that's the address the remote agents dial. It isn't bound to the Tailscale IP, because Docker would start Core before `tailscale0` came up at boot and the bind would fail.
- **The `proxy` Docker network** — must be created on each host before any stack deploys (`docker network create proxy`). Not needed on kirks-bar, which has no Traefik of its own: its stacks publish ports and get static routes in `traefik/config.yml`.
- **The NVIDIA driver and container toolkit on kirks-bar** — installed by the ansible repo's `nvidia.yml` (driver branch `580-server`, the last with Pascal support). Kernel and driver updates are kept out of unattended-upgrades and applied by its `updates.yml`, which reboots.

## Architecture

- **GitOps tooling:** [Komodo](https://github.com/moghtech/komodo). A Core-wide procedure, "Deploy Changed Stacks", runs every 5 minutes and redeploys only stacks whose compose files changed in this repo. Image polling ("Global Auto Update") runs once a day, since every tag is pinned. Locally built stacks (`build:`) need `run_build: true`, `auto_pull: false`, and every file in their build context listed in the stack's `config_files`, or a commit that changes only those files won't deploy.
- **Reverse proxy:** [Traefik v3](stacks/nelson-nuc/traefik) fronts everything. Dockerized services route in via labels; non-Docker upstreams (Proxmox, the router, the NAS, UniFi, and the quark-vm-hosted services) are registered as static routes in `traefik/config.yml` instead. The shared external Docker network is named `proxy` — every container that needs Traefik routing must join it.
- **Tailscale:** nelson-nuc advertises the LAN (`192.168.88.0/24`) as a subnet route. Servers on that LAN (anything that receives LAN connections: kirks-bar, quark-vm, etc.) must run with `tailscale set --accept-routes=false`: accepting the route sends their replies to LAN connections out `tailscale0` instead of the NIC, so SSH, Ansible, and anything else reaching them by LAN address times out (hit on kirks-bar, 2026-09-26). Roaming clients are the opposite. The laptop (framework) keeps `--accept-routes=true` so the LAN works remotely, and a NetworkManager hook in [laptop-dotfiles](https://github.com/nph4/laptop-dotfiles) (`etc/NetworkManager/dispatcher.d/50-home-lan-local`) adds a higher-priority `ip rule` at home so LAN traffic stays local instead of going through Tailscale. The tailnet's split DNS sends `local.nelsonhickman.com` to Pi-hole's LAN IP `192.168.88.34`, so a client without the route can't resolve those names off the LAN.
- **TLS:** wildcard certs via Cloudflare DNS challenge (cert resolver `cloudflare`). Internal-only services live under `*.local.nelsonhickman.com`; anything internet-facing is under `*.nelsonhickman.com`.
- **Secrets:** two patterns, both always an absolute host path (never relative: the deploy tool runs compose from its own Git clone, and anything outside the clone must be visible to Komodo's Periphery agent, under `/home/nelson/containers` on nelson-nuc):
  - Docker `secrets:` block pointing at a file on the host, e.g. `/home/nelson/containers/traefik/cf_api_token.txt` (used by traefik, nextcloud)
  - `env_file:` pointing at a file on the host, e.g. `/home/nelson/containers/mealie/.env` (used when the upstream image expects env vars)
- **Image versions:** pinned to explicit versions everywhere, e.g. `traefik:v3.0.4`, `postgres:16`, `nextcloud:31-apache`. `ghcr.io/vert-sh/vert` intentionally stays on `latest` because it publishes no versioned tags. Stacks built from a local `Dockerfile` (`build: .`) pin their base image and packages there instead, and tag the image with the version, e.g. `ansible-control:14.4.0` (the `ansible` package version). Under Komodo they also need `pull_policy: build`, since Komodo runs `docker compose pull` first and would fail trying to pull the local tag from Docker Hub.
- **Volumes:** named Docker volumes for stateful data; bind mounts under `/home/nelson/containers/<stack>/` on nelson-nuc, `/srv/<stack>/` on quark-vm, and `/home/kirk/containers/<stack>/` on kirks-bar.
- **Timezone:** every container sets `TZ=America/Los_Angeles` in its `environment` block.
- **Database backups:** a nightly job on each host (02:30, the [ansible repo](https://github.com/nph4/homelab-ansible)'s `db-backup.yml`) dumps every container labeled `homelab.backup.postgres=true` (`pg_dumpall`) or `homelab.backup.sqlite=<container paths, comma-separated>` (SQLite online backup) to `/mnt/nas/backups/db/<host>/<date>/`, keeping 14 days. It runs before CrashPlan's 03:00 scan of the NAS, so the dumps also go offsite. This covers databases only, not the files apps keep next to them (uploads, images, documents). The log is `/var/log/db-backup.log` on each host.

## Services

**nelson-nuc**

| Stack | What it is |
|---|---|
| `traefik` | Reverse proxy / TLS termination for everything else |
| `cloudflared` | Cloudflare Tunnel connector for internet-facing services |
| `mealie` | Recipe manager & meal planner |
| `nextcloud` | File sync / groupware |
| `home-assistant` | Home automation hub |
| `unifi` | UniFi network controller |
| `dashy` | Homepage / dashboard for all the above |
| `uptime-kuma` | Uptime monitoring |
| `dozzle` / `dozzle-agent` | Live Docker log viewer (agent also runs on quark-vm) |
| `homebox` | Home inventory / asset tracker |
| `wallos` | Subscription & recurring-expense tracker |
| `adventurelog` | Travel / trip logging |
| `reactive-resume` | Resume builder |
| `calibre-web` | Ebook library / reader |
| `it-tools` | Self-hosted collection of developer utilities |
| `vert` | File format converter |
| `ansible` | Persistent Ansible control container with a browser-based terminal (`ttyd`) into it |
| `days-since-incident` | Small custom-built "days since last incident" counter |

**quark-vm**

| Stack | What it is |
|---|---|
| `paperless` | Document management ([paperless-ngx](https://github.com/paperless-ngx/paperless-ngx)) |
| `crashplan` | CrashPlan backup client |
| `dozzle-agent` | Log agent feeding nelson-nuc's `dozzle` |

**kirks-bar**

| Stack | What it is |
|---|---|
| `jellyfin` | Media server, NVENC transcoding on the Quadro P1000. Routed by a static entry in `traefik/config.yml`, since Traefik can't read Docker labels on another host |
| `dozzle-agent` | Log agent feeding nelson-nuc's `dozzle` |

## Adding a service

1. Create `stacks/<host>/<service-name>/docker-compose.yml`
2. Join the `proxy` network (`external: true`)
3. Add Traefik labels for routing and TLS — use an existing stack as a template
4. If the service needs secrets, create a `secrets/` directory with `*-example` placeholder files
5. If the service needs env vars beyond what labels cover, create a `.env-example` and place the real `.env` at `/home/nelson/containers/<service>/.env` on nelson-nuc
6. For non-Docker upstreams (host IPs, Tailscale IPs), add a router + service entry to `stacks/nelson-nuc/traefik/config.yml`
7. Use absolute paths for all volume mounts, env_file references, and secret files
8. Set `TZ=America/Los_Angeles` in the `environment` block. If it has a Postgres or SQLite database, add the matching `homelab.backup.*` label (see Architecture)
9. Add a Pi-hole Local DNS record for the `*.local.nelsonhickman.com` hostname, pointing at `192.168.88.101` (Traefik). Internet-facing hostnames also need a Cloudflare Tunnel public hostname and DNS record
10. Create the stack in Komodo on the right server: repo `nph4/Homelab-IaC`, branch `main`, run directory `stacks/<host>/<service-name>`, file path `docker-compose.yml`. For a `build:` stack, also set `run_build: true` and `auto_pull: false`, and list its build-context files under `config_files`. Then deploy it once; after that, commits deploy within 5 minutes

## More context

[`CLAUDE.md`](CLAUDE.md) is Claude Code's working notes for this repo: a detailed log of what broke, what got fixed, and why. Worth checking if a service starts behaving unexpectedly after a redeploy, since it often explains prior drift between what's live and what's in the repo. [`Komodo-Migration.md`](Komodo-Migration.md) and [`Komodo-PoC.md`](Komodo-PoC.md) record how the repo moved to its current deploy tool.

## Long-Term TODO
- Implement an authentication suite
- Set-up log shipping for items not in docker
- Setup full-blown Gitops, CI/CD pipeline
