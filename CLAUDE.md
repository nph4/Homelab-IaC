# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Infrastructure-as-Code for a personal homelab. All services run as Docker Compose stacks inside of Portainer, grouped by host machine. There is no build system, CI pipeline, or test suite. Each compose file corresponds to a "stack" in Portainer.

**IaC migration is in progress.** The goal is to have Portainer deploy all stacks directly from this Git repo (GitOps mode) rather than managing them via the Portainer web editor. See the IaC Migration Status section below.

## Repository layout

```
stacks/
  nelson-nuc/   # Intel NUC, primary host — most services live here
  quark-vm/     # Proxmox VM (Tailscale IP 100.76.105.3) — paperless, crashplan, dozzle-agent
```

Each service is a subdirectory containing a `docker-compose.yml` and optionally a `.env-example` or `secrets/` example file.

## Architecture patterns

**Reverse proxy:** All services route through Traefik v3 (`stacks/nelson-nuc/traefik/`). Services expose themselves via Docker labels; non-Docker services (Proxmox, Portainer, router, NAS) are registered as static upstreams in `traefik/config.yml`. The shared external Docker network is named `proxy` — every container that needs Traefik routing must join it.

**TLS:** Wildcard certs via Cloudflare DNS challenge. The cert resolver is named `cloudflare`. Local services use `*.local.nelsonhickman.com`; internet-facing services use `*.nelsonhickman.com`.

**Secrets:** Two patterns are used:
- Docker secrets (`secrets:` block with an absolute path to a file on the host, e.g. `/home/nelson/containers/traefik/cf_api_token.txt`) — used for traefik and nextcloud
- `env_file` with an absolute host path (e.g. `env_file: /home/nelson/containers/mealie/.env`) — used when the upstream image expects env vars

Always use absolute paths for both — relative paths break when Portainer deploys from a Git clone. Secret files are never committed; `.env-example` and `secrets/*-example` files document what values are needed.

**Image versions:** All images are pinned to explicit versions (never `latest`), e.g. `traefik:v3.0`, `postgres:16`, `nextcloud:31-apache`. Two images intentionally stay on `latest` because they publish no versioned tags: `ghcr.io/vert-sh/vert` and `peco602/ansible-linux-docker`.

**Volumes:** Named Docker volumes for stateful data; bind mounts under `/home/nelson/containers/<stack>/` on nelson-nuc, and `/srv/<stack>/` on quark-vm.

**Timezone:** All containers must include `TZ=America/Los_Angeles` in their `environment` block.

## Adding a new service

1. Create `stacks/<host>/<service-name>/docker-compose.yml`
2. Join the `proxy` network (external: true)
3. Add Traefik labels for routing and TLS — use an existing stack as a template
4. If the service needs secrets, create a `secrets/` directory with `*-example` placeholder files
5. If the service needs env vars beyond what labels cover, create a `.env-example` and place the real `.env` at `/home/nelson/containers/<service>/.env` on nelson-nuc
6. For non-Docker upstreams (host IPs, Tailscale IPs), add a router + service entry to `stacks/nelson-nuc/traefik/config.yml`
7. Use absolute paths for all volume mounts, env_file references, and secret files
8. Set `TZ=America/Los_Angeles` in the `environment` block

## IaC Migration Status

**What runs manually (will always be bootstrapped by hand):**
- Portainer itself — must exist before it can manage anything
- The `proxy` Docker network — must be created on the host before any stack deploys (`docker network create proxy`)

**Phase 1 — complete:** All image versions pinned; relative `env_file: .env` references removed; compose files audited for absolute volume paths.

**Phase 2 — mostly complete:** Secrets strategy settled (absolute-path env_file + Docker secrets). Traefik compose was truncated in the repo and has been restored. Nextcloud secret path fixed to absolute. Portainer now has `/home/nelson/containers:/home/nelson/containers:ro` mounted into its own container (recreated 2026-08-22, confirmed via `docker inspect`), resolving the blocker that kept it from seeing absolute-path `env_file:` targets. Mealie (`env_file: /home/nelson/containers/mealie/.env`) and cloudflared (`env_file: /home/nelson/containers/cloudflared/.env`) have both been retested via live GitOps redeploys and confirmed working — mealie via clean logs and normal request traffic, cloudflared via a zero-downtime dual-connector cutover (temporarily renamed to `cloudflared-git` to run alongside the old container, verified healthy, then reverted — the revert redeploy also confirmed Portainer correctly re-pulls and applies upstream repo changes, not just initial deploys).

**Remaining for Phase 2:**
- `traefik` — `CF_DNS_API_TOKEN_FILE` already uses an absolute-path Docker secret (fine as-is now). But `TRAEFIK_DASHBOARD_CREDENTIALS` is also baked into a `labels:` entry (`traefik.http.middlewares.traefik-auth.basicauth.users=${TRAEFIK_DASHBOARD_CREDENTIALS}`) via Compose-level `${VAR}` substitution — that requires a `stack.env` committed to the repo for Repository-mode GitOps, which isn't viable since the repo is public. Needs a redesign: move dashboard basic-auth off the label and into Traefik's dynamic file config (`config.yml`) using `basicAuth.usersFile` pointing at an absolute-path htpasswd file, matching the existing Docker-secret pattern. In progress.
- `reactive-resume` — uses `${VAR}` substitution across 4 services, including values composed into other values (e.g. `DATABASE_URL` embedding `${POSTGRES_PASSWORD}`) and the same secret reused under different variable names per service. Needs consolidation into a single literal `.env` (env_file can't do string interpolation, so composed/reused values must be written out explicitly per key). Note: an upstream commit ("rective resume fix", 2026-06-28) changed this stack's `docker-compose.yml` and trimmed its `FIXME.md` after the analysis above was done — re-read current state before converting.

**Phase 3 — in progress:** Connect each stack to Portainer GitOps (repo URL `https://github.com/nph4/Homelab-IaC`, branch `main`). No PAT is configured or needed — the repo is public, so anonymous HTTPS pulls work fine (only relevant if the repo goes private, or anonymous rate limits become an issue). Done: `mealie`, `cloudflared`. Suggested order for the rest: it-tools → vert → homebox → dashy → uptime-kuma → dozzle → wallos → calibre-web → reactive-resume → jellyfin → adventurelog → unifi → home-assistant → nextcloud → traefik → days-since-incident.

**Phase 4 — not started:** Set up GitHub webhooks pointing at Portainer per-stack webhook URLs for automatic redeployment on push.
