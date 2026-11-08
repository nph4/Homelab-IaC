# CLAUDE.md

Standing rules for working in this repo. Keep this file short: it's loaded into every session.

- **[`README.md`](README.md)** is the source of truth: architecture, conventions, service inventory, adding a service, SSO.
- **BookStack** (`https://docs.local.nelsonhickman.com`, book *Exceptions (not in Git)*, plus *Runbooks* and *Projects*) holds everything outside Git: hosts, DNS, Cloudflare, secrets locations, Komodo's app config, in-app settings, workstations, the router. **New outside-Git state goes there.** API token on the workstation at `~/.bookstack-creds` (`ID=`/`SECRET=`, header `Authorization: Token <id>:<secret>`; expires about 2027-01-03).
- **[`docs/history.md`](docs/history.md)** is the dated log of what broke and why (it was this file until 2026-11-08). Search it when something behaves unexpectedly; **append new history entries there, not here.** Add a line below only for a rule that should change how future work is done.

## Hosts and access

- SSH: `nelson@nelson-nuc`, `quark@quark-vm`, `kirk@kirks-bar` (not `nelson@`). No passwordless sudo on nelson-nuc or quark-vm; for root-owned files inside a container's data, use `docker exec <container> ...`. kirks-bar via Ansible when the direct key fails: `docker exec -w /ansible/homelab-ansible ansible ansible kirks-bar.lan -b -m shell -a '...'` on nelson-nuc (always pass `-w /ansible/homelab-ansible`, or it won't find the inventory).
- Claude Code runs on nelson-desktop or framework; check `hostname` before assuming a credential file is there.
- **Komodo** (deploys every stack; Portainer is gone): `https://komodo.local.nelsonhickman.com`, or `192.168.88.101:9120`. API key in `~/.komodo-key` (`Key=`/`Secret=`, headers `X-Api-Key`/`X-Api-Secret`), calls are `POST /read|/write|/execute` with `{"type","params"}`. `DeployStack` returns an Update; poll `GetUpdate` until `status` is `Complete`. Login route if ever needed: `POST /auth/login/LoginLocalUser` with bare `{username,password}`; the JWT is at `.data.jwt`.
- Server names in Komodo: `10-forward` (nelson-nuc), `quark-vm`, `kirks-bar`. Renaming a server also needs the agent's connect-as name changed.

## Deploying stacks

- The procedure **"Deploy Changed Stacks"** deploys pushed compose changes every 5 min. Other files only count if they're in the stack's `config_files` **with `requires: Redeploy`** (the default `None` is ignored). "Global Auto Update" only re-pulls same-tag images, daily at 03:00; don't shorten it (Docker Hub's anonymous rate limit).
- Commit and push repo-side fixes **before** a deploy can pick up the old commit.
- **Config files go in through a `build:` context** (`COPY` in a Dockerfile, like `dashy` and `auth/authelia`), never a relative bind mount: Komodo's clone doesn't provide sibling files to `volumes:`. `build:` stacks need `auto_pull: false`.
- **Periphery runs `docker compose` inside its own container.** Absolute host paths in `env_file:`/`secrets: file:` must be under `/home/nelson/containers` (nelson-nuc), `/home/quark/containers` or `/opt/stacks/paperless-ngx/secrets` (quark-vm), `/home/kirk/containers` (kirks-bar). Check this before every new stack.
- **Named volumes:** if a stack's live volume was created under a different project name, pin it with `name:` + `external: true`, or a deploy silently creates an empty one (happened to uptime-kuma, days-since-incident, mealie). Diff the live volume before connecting/renaming any stateful stack.
- Pin image tags; verify a tag exists (`docker pull`) and that a pin matches what's running before a "no-op" cutover. Never bump a version as a side effect of a tooling change (Home Assistant precedent).
- Back up before risky changes: SQLite cold (container stopped), Postgres with a live `pg_dump`. Verify data by restoring into a throwaway container; write SQL to a file instead of quoting it through `ssh`/`sh -c`.
- Validate risky config in a throwaway container first (e.g. `authelia validate-config` / `access-control check-policy`), not on the live stack.
- Traefik's `traefik.yml`/`config.yml` are bind-mounted from `/home/nelson/containers/traefik/data/`: sync the host copy **in place** (not `mv`) after a repo change; static config needs a restart. Rewriting `config.yml` briefly breaks `@file` middlewares; check for `ERR` lines after. Never touch `acme.json`.
- A new public `*.nelsonhickman.com` hostname also needs a cloudflared tunnel ingress rule plus a proxied CNAME (Cloudflare, via the `cloudflare` plugin), and must be smoke-tested from outside the LAN (`curl --resolve <host>:443:<cloudflare-ip>`): Pi-hole overrides hide the gap at home.

## SSO (Authelia + LLDAP, stack `auth`)

- Forward-auth cutover checklist, for every site: Traefik label `middlewares=authelia@docker`; add the hostname to `&forward_auth_sites` in `auth/authelia/configuration.yml` (default policy is deny); set **HTTP Basic Auth** with the LLDAP `monitoring` account `uptime-kuma` on its Uptime Kuma monitor (the user does this in Kuma's UI); add `statusCheckHeaders` with the `__MONITORING_BASIC_AUTH__` placeholder to its Dashy tile. Test in a private window (PWAs serve from cache).
- Changing Authelia's config restarts it and logs everyone out. Three wrong passwords in 2 min ban a user for 10 min.
- Never trust Docker ranges as `internal`: public traffic arrives from cloudflared (`172.29.0.20`). `172.29.0.1` is trusted only while cloudflared's ingress targets `https://traefik:443`.
- Apps with mobile clients use OIDC (policy `homelab`), not forward-auth. Plan and progress: BookStack *Projects → SSO: Authelia + LLDAP*.

## Host gotchas

- **nelson-nuc runs kernel 7.x: never go back to a `mongo:8.0` tag** for Komodo (crash-loops); it's pinned to 8.2.x.
- Before any Ubuntu release upgrade: `apt-mark showauto docker.io containerd runc`; if listed, `sudo apt-mark manual docker.io` (the upgrade's autoremove deleted Docker on quark-vm).
- Bind services to LAN IPs, not Tailscale IPs: Tailscale comes up after Docker at boot.
- A container binding a **subdirectory** of `/mnt/nas` doesn't see a remount; `nas-remount-restart.service` (homelab-ansible) restarts those containers. Don't make media binds `:ro` (Jellyfin writes metadata).
- Scheduled jobs avoid 01:00–03:00 (DST). Test cron jobs through cron, not by running the script; quote empty env values in `/etc/cron.d` files.
- Pi-hole config from scripts: `sudo pihole-FTL --config ...`, not the API. If the two Pi-holes disagree, check `docker logs nebula-sync` on quark-vm first.
- Servers and their containers resolve `*.local.nelsonhickman.com` through Tailscale split DNS, not the NIC's DNS servers; restarting containers doesn't pick up DNS changes. Tailscale `--accept-routes=false` on LAN servers and nelson-desktop; framework keeps `true` plus its home-LAN `ip rule` hook.
- Failover/outage tests: run checks in parallel with short timeouts and confirm by timestamp they fell inside the outage.
- Don't bulk-delete dpkg obsolete conffiles; only a renamed replacement in a read-as-a-whole directory (the logrotate/cloud-init case) is a problem.

## Conventions for Claude

- `TZ=America/Los_Angeles` in every stack; report times in Pacific, never UTC.
- Spell out "Home Assistant" (never "HA", which means High Availability).
- Never print secret files, even through a redaction `sed`; show key names and value lengths only. Give the user commands to read a secret in their own terminal (not via `!`).
- If the approach of an approved plan changes, stop and ask again.
