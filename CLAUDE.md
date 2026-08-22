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

`traefik` is now fully done (2026-08-22): the `TRAEFIK_DASHBOARD_CREDENTIALS` label required a `stack.env` committed to the repo for Repository-mode GitOps, not viable in a public repo, so dashboard basic-auth was moved off the label into `config.yml`'s file-provider middleware (`traefik-auth: basicAuth.usersFile: /run/secrets/traefik_dashboard_htpasswd`), backed by a new Docker secret (same pattern as `cf_api_token`). Host-side files (`dashboard_htpasswd.txt`, synced `config.yml`) were created/updated on nelson-nuc, then redeployed and confirmed via Portainer — see Phase 3 below. Along the way, also fixed a `.gitignore` bug where `**/secrets/` excluded the whole directory and silently defeated the `!**/secrets/*-example` negation underneath it — NextCloud's example secret file had never actually been committed as a result; now fixed (`**/secrets/*`) and both traefik's and NextCloud's `*-example` files are tracked.

**Remaining for Phase 2:**

- `reactive-resume` — **repo-side conversion done (2026-08-22, see `stacks/nelson-nuc/reactive-resume/FIXME.md` Issue 3), host-side redeploy/confirm not yet done.** `${VAR}` substitution across services replaced with a single shared `env_file: /home/nelson/containers/reactive-resume/.env` (same pattern as adventurelog); composed values (`DATABASE_URL`, `STORAGE_ACCESS_KEY`/`STORAGE_SECRET_KEY`) written out literally since `env_file` can't interpolate. `CHROME_TOKEN`/`TOKEN` no longer exist in this stack (removed earlier per FIXME Issue 2 — unrelated to this pass). Host `.env` created at `/home/nelson/containers/reactive-resume/.env` with live values pulled via `docker inspect` on the running containers (the old on-disk `.env` under `/home/nelson/stacks/reactive-resume/` was stale — `AUTH_SECRET`/`MAIL_FROM` were actually set via Portainer's env var UI, not that file). **Still to do:** redeploy via Portainer's local editor (not GitOps-connected yet) with the updated compose + new env_file path, confirm the app works end-to-end (login, editor, PDF export, storage), then connect to GitOps.

**Phase 3 — in progress:** Connect each stack to Portainer GitOps (repo URL `https://github.com/nph4/Homelab-IaC`, branch `main`). No PAT is configured or needed — the repo is public, so anonymous HTTPS pulls work fine (only relevant if the repo goes private, or anonymous rate limits become an issue). Done: `mealie`, `cloudflared`, `traefik` (2026-08-22 — redeployed via Portainer GitOps at commit `1c8a46b`, `docker inspect` confirms `com.docker.compose.project.config_files` pointing at the Portainer-managed Git clone, pinned `v3.0.4`, dashboard auth now `traefik-auth@file` with no leftover label-based basicauth, clean logs). Note: `config.yml`/`traefik.yml`/`acme.json` are still bind-mounted from `/home/nelson/containers/traefik/data/` on the host rather than sourced from the Git clone directly — future repo changes to `config.yml` still need manual host sync (see Phase 2 note above). Suggested order for the rest: it-tools → vert → homebox → dashy → uptime-kuma → dozzle → wallos → calibre-web → reactive-resume → jellyfin → adventurelog → unifi → home-assistant → nextcloud → days-since-incident.

**Phase 4 — not started:** Set up GitHub webhooks pointing at Portainer per-stack webhook URLs for automatic redeployment on push.
