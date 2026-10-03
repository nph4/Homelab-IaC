# Homelab-IaC

Infrastructure-as-Code for my homelab. Every service runs as a Docker Compose stack, deployed and managed via GitOps rather than by hand through a web UI — by [Komodo](https://github.com/moghtech/komodo) (until 2026-10-03, by [Portainer](https://www.portainer.io/); see below). Komodo pulls each compose file directly from this repo and redeploys a stack within 5 minutes of a commit that changes it. There's no build system, CI pipeline, or test suite; a compose file in this repo *is* the deployment.

## Migrated off Portainer to Komodo (complete 2026-10-03)

Portainer 3.0 drops the standalone Community Edition build. 2.x keeps getting security patches, but no new features; the only forward path (3.x) gates multi-host and GitOps behind a capped "3 Nodes Free" tier of the Business Edition, not a FLOSS release. Since a free/libre offering is a hard requirement here, this repo needs to move off Portainer before 2.x support ends.

Chosen migration target: **[Komodo](https://github.com/moghtech/komodo)** (GPL-3.0) — closest architectural match to this repo's model of git-tracked compose stacks deployed across multiple hosts, with no paywalled GitOps or multi-host features, and (confirmed 2026-09-19) no paid tier of any kind. Alternatives considered: [Coolify](https://github.com/coollabsio/coolify) (Apache-2.0, more PaaS-flavored, heavier lift) and CapRover (Apache-2.0, also PaaS-flavored).

**PoC (2026-09-12 to 2026-09-14): all 9 planned steps passed.** Core + Mongo stood up on nelson-nuc, Periphery agents connected on both nelson-nuc and quark-vm from that one Core, a throwaway duplicate `it-tools` stack deployed and redeployed via a real git push (verified by the deployed commit hash advancing, not just "the page loads"), and a second throwaway stack proven on quark-vm — all without touching any real Portainer-managed stack. Full detail in [`Komodo-PoC.md`](Komodo-PoC.md); research notes in [`CLAUDE.md`](CLAUDE.md).

One thing to weigh before committing to a real migration: **auto-redeploy cadence is coarser than Portainer's out of the box.** Komodo's default is a single daily scheduled job (3am), not Portainer's continuous 5-minute poll — proven working here by invoking that job's action directly rather than waiting for it to fire. A real migration needs either a shorter schedule or a defined manual/webhook-triggered pattern between runs.

**Stateful follow-up PoC (2026-09-19): both hard patterns validated.** The uptime-kuma/mealie external-volume-pinning trick works identically under Komodo, no changes needed. Absolute-path `env_file`/Docker `secrets:` hit a real blocker — Komodo's Periphery agent runs `docker compose` as a subprocess inside its own container and (unlike Portainer) couldn't see any host path outside its mounted root — fixed once by adding a read-only `/home/nelson/containers` mount to Periphery, mirroring the fix Portainer itself needed in Phase 2. Detail in `Komodo-PoC.md`'s "Follow-up" section.

**GUI walkthrough (2026-09-19): confirmed usable.** A real hands-on comparison found every Portainer GUI operation used day to day (logs, redeploy, deployed-commit visibility, drift) has a Komodo equivalent — names and layout differ, expected friction from switching stacks, not a functional gap.

**All three PoC success criteria are now met, and the three throwaway PoC stacks have been torn down** (only the reusable Core/Mongo/Periphery infrastructure remains) — see `Komodo-PoC.md`'s "Success criteria" and "Rollback / cleanup" sections. The PoC has answered the question it set out to answer.

**Migration timeline decided (2026-09-19): see [`Komodo-Migration.md`](Komodo-Migration.md).** Portainer's own [lifecycle page](https://docs.portainer.io/start/lifecycle) confirms 2.45 LTS (the version running here) loses security-patch support **May 2027** — real deadline, not the earlier unverified "~6 months" estimate. Plan: ~2hr biweekly sessions, bulk of the 21 routine stacks migrated by end of 2026, with `traefik` and `home-assistant` (highest blast radius / most recently touched) deliberately held for a January–April 2027 troubleshooting buffer ahead of the deadline. Repo changes deploy through a Komodo procedure, "Deploy Changed Stacks", that runs every 5 minutes and redeploys only stacks whose files changed (Komodo's own "Global Auto Update" only reacts to new images under the same tag, so it doesn't cover this), and Komodo Core is now reachable at `https://komodo.local.nelsonhickman.com` through Traefik.

**Session 1 complete (2026-09-19): 6 of 21 routine stacks cut over** (`it-tools`, `dozzle`, `dozzle-agent` on both hosts, `vert`, `homebox`) — all verified healthy, three with zero downtime. Established the real cutover mechanics (disable Portainer polling via its API, match the Komodo Stack's Docker Compose project name for an in-place recreate) that the remaining sessions will reuse. Detail in `Komodo-Migration.md`.

**Session 2 complete (2026-10-03): 10 of 21** (`unifi`, `wallos`, `calibre-web`, `dashy`), all healthy with their existing data reattached.

**Session 3 complete (2026-10-03): 14 of 21** (`days-since-incident`, `uptime-kuma`, `mealie`, `nextcloud`), all with their existing data confirmed intact.

**Session 4 complete (2026-10-03): 17 of 21** (`cloudflared`, `adventurelog`, `reactive-resume`). Every routine nelson-nuc stack is now on Komodo; Portainer there manages only `traefik` and `home-assistant`.

**Session 5 complete (2026-10-03): 19 of 21** (`crashplan`, `paperless` on quark-vm). Every routine stack is on Komodo.

**`home-assistant` migrated early (2026-10-03): 20 of 21.**

**`traefik` migrated (2026-10-03): all 21 stacks are on Komodo.**

**Portainer decommissioned (2026-10-03).** The server container and image on nelson-nuc are removed, as are its Traefik route and dashy tile. Its data volume is kept, with a tar backup in `~/portainer-backup/`. The quark-vm agent was removed earlier the same day.

## Layout

```
stacks/
  nelson-nuc/   # Intel NUC, primary host — most services live here
  quark-vm/     # Proxmox VM (Tailscale IP 100.76.105.3) — paperless, crashplan, dozzle-agent
  kirks-bar/    # OptiPlex 7040 + Quadro P1000 (192.168.88.23, Tailscale IP 100.110.243.115), GPU host — jellyfin, dozzle-agent
```

Each subdirectory under `stacks/<host>/` is one GitOps stack: a `docker-compose.yml`, plus (where needed) a `.env-example` and/or `secrets/*-example` file documenting what real values are expected. Actual secrets and `.env` files are never committed — they live directly on the host at an absolute path the compose file references. Every stack is deployed by Komodo; see [`Komodo-Migration.md`](Komodo-Migration.md) for how each was cut over.

## What runs manually

A few things are always bootstrapped by hand, not by GitOps, since they're prerequisites for GitOps itself:
- **Komodo Core, its Mongo database, and the Periphery agent on each host** — deployed at `/home/nelson/containers/komodo/` on nelson-nuc, deliberately kept outside this repo, since it's what deploys the repo. This is the replacement for Portainer, itself bootstrapped and run by hand the same way Portainer is; Periphery is what actually executes `docker compose` on each host on Komodo's behalf. kirks-bar (192.168.88.23, Ubuntu 26.04) runs a standalone Periphery as `kirk`, deployed by the [ansible repo](https://github.com/nph4/homelab-ansible)'s `komodo-periphery.yml` rather than by hand. Core's port is bound to nelson-nuc's LAN IP (`192.168.88.101:9120`), and that's the address the remote agents dial. It isn't bound to the Tailscale IP, because Docker would start Core before `tailscale0` came up at boot and the bind would fail.
- **The `proxy` Docker network** — must be created on each host before any stack deploys (`docker network create proxy`). Not needed on kirks-bar, which has no Traefik of its own: its stacks publish ports and get static routes in `traefik/config.yml`.
- **The NVIDIA driver and container toolkit on kirks-bar** — installed by the ansible repo's `nvidia.yml` (driver branch `580-server`, the last with Pascal support). Kernel and driver updates are kept out of unattended-upgrades and applied by its `updates.yml`, which reboots.

## Architecture

- **GitOps tooling:** [Komodo](https://github.com/moghtech/komodo). A Core-wide procedure, "Deploy Changed Stacks", runs every 5 minutes and redeploys only stacks whose compose files changed in this repo. Image polling ("Global Auto Update") runs once a day, since every tag is pinned. Locally built stacks (`build:`) need `run_build: true` and `auto_pull: false`.
- **Reverse proxy:** [Traefik v3](stacks/nelson-nuc/traefik) fronts everything. Dockerized services route in via labels; non-Docker upstreams (Proxmox, the router, the NAS, UniFi, and the quark-vm-hosted services) are registered as static routes in `traefik/config.yml` instead. The shared external Docker network is named `proxy` — every container that needs Traefik routing must join it.
- **Tailscale:** nelson-nuc advertises the LAN (`192.168.88.0/24`) as a subnet route. Servers on that LAN (anything that receives LAN connections: kirks-bar, quark-vm, etc.) must run with `tailscale set --accept-routes=false`: accepting the route sends their replies to LAN connections out `tailscale0` instead of the NIC, so SSH, Ansible, and anything else reaching them by LAN address times out (hit on kirks-bar, 2026-09-26). Roaming clients are the opposite. The laptop (framework) keeps `--accept-routes=true` so the LAN works remotely, and a NetworkManager hook in [laptop-dotfiles](https://github.com/nph4/laptop-dotfiles) (`etc/NetworkManager/dispatcher.d/50-home-lan-local`) adds a higher-priority `ip rule` at home so LAN traffic stays local instead of going through Tailscale. The tailnet's split DNS sends `local.nelsonhickman.com` to Pi-hole's LAN IP `192.168.88.34`, so a client without the route can't resolve those names off the LAN.
- **TLS:** wildcard certs via Cloudflare DNS challenge (cert resolver `cloudflare`). Internal-only services live under `*.local.nelsonhickman.com`; anything internet-facing is under `*.nelsonhickman.com`.
- **Secrets:** two patterns, both always an absolute host path (never relative: the deploy tool runs compose from its own Git clone, and anything outside the clone must be visible to Komodo's Periphery agent, under `/home/nelson/containers` on nelson-nuc):
  - Docker `secrets:` block pointing at a file on the host, e.g. `/home/nelson/containers/traefik/cf_api_token.txt` (used by traefik, nextcloud)
  - `env_file:` pointing at a file on the host, e.g. `/home/nelson/containers/mealie/.env` (used when the upstream image expects env vars)
- **Image versions:** pinned to explicit versions everywhere, e.g. `traefik:v3.0`, `postgres:16`, `nextcloud:31-apache`. `ghcr.io/vert-sh/vert` intentionally stays on `latest` because it publishes no versioned tags. Stacks built from a local `Dockerfile` (`build: .`) pin their base image and packages there instead, and tag the image with the version, e.g. `ansible-control:14.4.0` (the `ansible` package version). Under Komodo they also need `pull_policy: build`, since Komodo runs `docker compose pull` first and would fail trying to pull the local tag from Docker Hub.
- **Volumes:** named Docker volumes for stateful data; bind mounts under `/home/nelson/containers/<stack>/` on nelson-nuc, `/srv/<stack>/` on quark-vm, and `/home/kirk/containers/<stack>/` on kirks-bar.
- **Timezone:** every container sets `TZ=America/Los_Angeles` in its `environment` block.

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
| `dozzle-agent` | Log agent feeding nelson-nuc's `dozzle` (Komodo-only, never on Portainer) |

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

## Long-Term TODO
- Implement an authentication suite
- Set-up log shipping for items not in docker
- Setup full-blown Gitops, CI/CD pipeline
