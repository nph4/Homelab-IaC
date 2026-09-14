# Homelab-IaC

Infrastructure-as-Code for my homelab. Every service runs as a Docker Compose stack, deployed and managed by [Portainer](https://www.portainer.io/) in GitOps mode — Portainer pulls each stack directly from this repo and polls it every few minutes to redeploy on new commits, rather than being edited by hand through Portainer's web UI. There's no build system, CI pipeline, or test suite; a compose file in this repo *is* the deployment.

## ⚠️ Migrating off Portainer (PoC complete, migration decision not yet made)

Portainer 3.0 drops the standalone Community Edition build. 2.x keeps getting security patches, but no new features; the only forward path (3.x) gates multi-host and GitOps behind a capped "3 Nodes Free" tier of the Business Edition, not a FLOSS release. Since a free/libre offering is a hard requirement here, this repo needs to move off Portainer before 2.x support ends.

Leading candidate: **[Komodo](https://github.com/moghtech/komodo)** (GPL-3.0) — closest architectural match to this repo's model of git-tracked compose stacks deployed across multiple hosts, with no paywalled GitOps or multi-host features. Alternatives considered: [Coolify](https://github.com/coollabsio/coolify) (Apache-2.0, more PaaS-flavored, heavier lift) and CapRover (Apache-2.0, also PaaS-flavored).

**PoC (2026-09-12 to 2026-09-14): all 9 planned steps passed.** Core + Mongo stood up on nelson-nuc, Periphery agents connected on both nelson-nuc and quark-vm from that one Core, a throwaway duplicate `it-tools` stack deployed and redeployed via a real git push (verified by the deployed commit hash advancing, not just "the page loads"), and a second throwaway stack proven on quark-vm — all without touching any real Portainer-managed stack. Full detail in [`Komodo-PoC.md`](Komodo-PoC.md); research notes in [`CLAUDE.md`](CLAUDE.md).

Two things to weigh before committing to a real migration:
- **Auto-redeploy cadence is coarser than Portainer's out of the box.** Komodo's default is a single daily scheduled job (3am), not Portainer's continuous 5-minute poll — proven working here by invoking that job's action directly rather than waiting for it to fire. A real migration needs either a shorter schedule or a defined manual/webhook-triggered pattern between runs.
- **The GUI comparison still needs a real walkthrough.** The PoC validated the underlying API (logs, redeploy, drift-detection via deployed-vs-latest commit hash) but no browser session was available to actually click through Komodo's UI side by side with Portainer's — don't treat that comparison as settled yet.

Not yet validated: the two hard patterns this repo actually depends on for stateful stacks — absolute-path `env_file`/Docker `secrets:`, and the uptime-kuma/mealie external-volume-pinning trick (see Architecture below and `CLAUDE.md`) — plus whether any Portainer feature in daily use here turns out to be Komodo Business-tier-gated. See `Komodo-PoC.md`'s "Follow-up" section.

## Layout

```
stacks/
  nelson-nuc/   # Intel NUC, primary host — most services live here
  quark-vm/     # Proxmox VM (Tailscale IP 100.76.105.3) — paperless, crashplan, dozzle-agent, portainer-agent
```

Each subdirectory under `stacks/<host>/` is one Portainer stack: a `docker-compose.yml`, plus (where needed) a `.env-example` and/or `secrets/*-example` file documenting what real values are expected. Actual secrets and `.env` files are never committed — they live directly on the host at an absolute path the compose file references.

## What runs manually

A couple of things are always bootstrapped by hand, not by GitOps, since they're prerequisites for GitOps itself:
- **Portainer** — must already exist before it can manage anything.
- **The `proxy` Docker network** — must be created on each host before any stack deploys (`docker network create proxy`).
- **The Portainer Agent on quark-vm** ([`stacks/quark-vm/portainer-agent`](stacks/quark-vm/portainer-agent)) — the pipe Portainer uses to reach that host. Its compose file is committed for version tracking, but it's applied on the host by hand rather than via GitOps, since redeploying it restarts the agent Portainer is mid-deploy through.

## Architecture

- **Reverse proxy:** [Traefik v3](stacks/nelson-nuc/traefik) fronts everything. Dockerized services route in via labels; non-Docker upstreams (Proxmox, Portainer, the router, the NAS, UniFi, and the quark-vm-hosted services) are registered as static routes in `traefik/config.yml` instead. The shared external Docker network is named `proxy` — every container that needs Traefik routing must join it.
- **TLS:** wildcard certs via Cloudflare DNS challenge (cert resolver `cloudflare`). Internal-only services live under `*.local.nelsonhickman.com`; anything internet-facing is under `*.nelsonhickman.com`.
- **Secrets:** two patterns, both always an absolute host path (never relative — Portainer deploys from a plain Git clone with no fixed working directory):
  - Docker `secrets:` block pointing at a file on the host, e.g. `/home/nelson/containers/traefik/cf_api_token.txt` (used by traefik, nextcloud)
  - `env_file:` pointing at a file on the host, e.g. `/home/nelson/containers/mealie/.env` (used when the upstream image expects env vars)
- **Image versions:** pinned to explicit versions everywhere, e.g. `traefik:v3.0`, `postgres:16`, `nextcloud:31-apache`. Two images intentionally stay on `latest` because they publish no versioned tags: `ghcr.io/vert-sh/vert` and `peco602/ansible-linux-docker`.
- **Volumes:** named Docker volumes for stateful data; bind mounts under `/home/nelson/containers/<stack>/` on nelson-nuc, and `/srv/<stack>/` on quark-vm.
- **Timezone:** every container sets `TZ=America/Los_Angeles` in its `environment` block.

## Services

**nelson-nuc**

| Stack | What it is |
|---|---|
| `traefik` | Reverse proxy / TLS termination for everything else |
| `cloudflared` | Cloudflare Tunnel connector for internet-facing services |
| `mealie` | Recipe manager & meal planner |
| `nextcloud` | File sync / groupware |
| `jellyfin` | Media server |
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
| `portainer-agent` | Portainer connectivity agent for this host (version tracks the Portainer server's LTS) |

## Adding a service

1. Create `stacks/<host>/<service-name>/docker-compose.yml`
2. Join the `proxy` network (`external: true`)
3. Add Traefik labels for routing and TLS — use an existing stack as a template
4. If the service needs secrets, create a `secrets/` directory with `*-example` placeholder files
5. If the service needs env vars beyond what labels cover, create a `.env-example` and place the real `.env` at `/home/nelson/containers/<service>/.env` on nelson-nuc
6. For non-Docker upstreams (host IPs, Tailscale IPs), add a router + service entry to `stacks/nelson-nuc/traefik/config.yml`
7. Use absolute paths for all volume mounts, env_file references, and secret files
8. Set `TZ=America/Los_Angeles` in the `environment` block

## More context

[`CLAUDE.md`](CLAUDE.md) is Claude Code's working notes for this repo — mainly a detailed log of the GitOps migration itself (what broke, what got fixed, and why). Worth checking if a service starts behaving unexpectedly after a redeploy, since it often explains prior drift between what's live and what's in the repo.
