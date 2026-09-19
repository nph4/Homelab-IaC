# Komodo Migration Plan

Status: **session 1 complete (2026-09-19), 6 of 21 routine stacks migrated.** This is the actual migration off Portainer, distinct from the completed proof-of-concept — see [`Komodo-PoC.md`](Komodo-PoC.md) for what was validated (both hard patterns, GUI usability, no paid tier) before this plan was written. See the README's "Migrating off Portainer" section for the high-level why.

## Warm-up: the `ansible` stack (2026-09-19, before session 1)

Ahead of the real migration sessions, the user manually deployed `ansible` (never previously run under Portainer, so zero cutover risk) through Komodo's GUI directly, to learn the workflow hands-on. Hit two real, unrelated bugs along the way — both now fixed and pushed:
- **File-extension typo:** Komodo's Stack config defaulted `file_paths` to `docker-compose.yaml`, but this repo's actual file is `docker-compose.yml` — "Validate Files" stage failed with a clear "Missing files" error. Fixed by editing the Stack's File Paths field in the GUI.
- **Real compose bug in the repo, exposed by this stack's first-ever deployment:** `ansible-terminal` (a `tsl0922/ttyd` web-terminal container) crash-looped immediately (`RestartCount` climbing, "the input device is not a TTY" on every attempt). Root cause: the image's entrypoint is `tini`, with a default `CMD` of `ttyd -W bash` — `ttyd` itself is part of the command, not baked into the entrypoint. The compose file's `command:` replaced that default with just `docker exec -it ansible bash`, dropping `ttyd` from the exec chain entirely, so the container's real PID 1 became the raw `docker exec` invocation with no pty. Fixed in the repo (`command: ["ttyd", "-W", "docker", "exec", "-it", "ansible", "bash"]`, commit `6b11b73`) — confirmed `RestartCount: 0` after redeploy, correct ttyd startup log, working web terminal.

Both fixes are useful evidence for the plan: Komodo's own failure reporting (stage-by-stage logs, clear error text) was sufficient to diagnose both issues without needing to fall back to raw `docker logs` digging for the first one.

## Why now, and the real deadline

Portainer server here runs **2.45 LTS**. Per [Portainer's own lifecycle page](https://docs.portainer.io/start/lifecycle), **2.45 LTS support (including security patches) ends May 2027** — confirmed directly, not the unverified "~6 months" figure carried in earlier research notes. From today (2026-09-19) that's **~8 months of runway**.

## Constraint this plan is built around

The user gets **~2 hours every other week** for homelab work — migration has to happen in short, infrequent bursts, not one continuous push. Stated goal: **get the bulk of the migration ("the heavy lifting") done by end of 2026**, leaving **January–April 2027 as a deliberate buffer** for in-depth troubleshooting on whichever specific stacks turn out to need it, well before the May 2027 deadline.

That gives roughly **7 biweekly sessions (~14 hours total)** between now and end of year for the routine work.

## Global prep (done 2026-09-19, ahead of session 1)

Komodo's `auto_update`/`poll_for_updates` stack flags are driven by one shared Core-wide Procedure ("Global Auto Update"), not a per-stack poll like Portainer's 5-minute default (see `Komodo-PoC.md` step 7 finding). **Decision: shorten it globally rather than rely on manual triggers**, since it applies to every stack at once and closest matches current Portainer behavior. Changed via `UpdateProcedure` from `"Every day at 03:00"` (English format) to **every 10 minutes**, Cron format `0 */10 * * * *`.

Worth remembering: the English-format shorthand `"Every 10 minutes"` silently produces an **invalid** Quartz cron expression in this Komodo version (`0 0/10 * * * ?` — the `english-to-cron` translation emits a single-number step `0/10`, which Komodo's own cron parser then rejects with "Invalid step syntax... use `*/10`"). The write still succeeds and looks fine until you check `ListProcedures`' `info.schedule_error` / `next_scheduled_run` (both silently null when it fails) — this is exactly the kind of "looks configured but isn't actually running" trap worth checking after any future schedule change. Fixed by switching `schedule_format` to `"Cron"` and providing `"0 */10 * * * *"` directly. Confirmed via `ListProcedures`: `schedule_error: null`, `next_scheduled_run` computed correctly on the next :00/:10/:20... mark.

## Session plan

Each session: pick the next stack group below, detach it from Portainer's GitOps (or just stop the Portainer stack once Komodo's copy is confirmed healthy — exact cutover mechanics to work out at the time, likely mirroring the dual-running pattern already used for `cloudflared` and `dashy-validate-test` during the original Portainer migration), create the Komodo Stack resource pointing at the same repo path, deploy, and verify against the same bar every stack was held to during the original Portainer GitOps migration: `docker inspect` sourced from the Git clone, correct image tag, `TZ` set, volumes/mounts attached to the *existing* data (not a fresh empty one), clean logs, working traffic through Traefik.

**Sessions 1–5 (target: complete by end of 2026) — 21 stacks, ordered easiest/lowest-risk to hardest within the routine set:**

1. **Stateless, no volumes, nothing host-specific to get wrong:** `it-tools`, `dozzle`, `dozzle-agent` (nelson-nuc), `dozzle-agent` (quark-vm), `homebox`, `vert`. (6 stacks — the it-tools POC already proved this exact shape works, so this session should move fast.)
2. **Static/simple routing, still no volumes:** `unifi` (static `config.yml` upstream, unaffected either way), `wallos`, `calibre-web`, `dashy` (already a `build:` context, same mechanism Komodo needs to prove for itself here). (4 stacks)
3. **Stateful — external volume names already known, no rediscovery needed** (see `CLAUDE.md` for the exact `external: true` pins already validated under Portainer): `uptime-kuma` (`uptime_kuma_uptime-kuma`), `days-since-incident` (`days-since-incident_data`), `mealie` (`mealie2_mealie-data`), `nextcloud` (4 services: app/db/redis/cron, no volume-name landmine but more moving parts). (4 stacks)
4. **Absolute-path `env_file` secrets — Periphery mount fix already proven in the stateful PoC:** `cloudflared`, `adventurelog`, `reactive-resume`. (3 stacks)
5. **Remaining quark-vm stacks + the one stack needing extra device-passthrough care:** `crashplan`, `paperless`, `jellyfin` (GPU passthrough — `/dev/dri`, render group, hwaccel — verify the same way the original migration did). (3 stacks)

That's 20 of the 21 routine stacks explicitly grouped above (`komodo` itself and `proxy` network are host prerequisites, not repo stacks). Pace works out to ~4 stacks/session across 5 sessions — sessions 1–2 should be fast enough to leave slack for whichever of sessions 3–5 runs long.

**Held back for the Jan–Apr 2027 buffer, deliberately not rushed into the EOY push:**
- **`traefik`** — reverse proxy for every other service in the repo; a bad cutover here has the highest blast radius of anything in this migration. Also already has its own known gotcha (`traefik.yml`/`config.yml` bind-mounted from the host, not Git-sourced — see `CLAUDE.md`) that deserves a careful pass, not a rushed one.
- **`home-assistant`** — completed a multi-month staged version upgrade only weeks ago (2026-08-31 to 2026-09-08) and was *just* reconnected to Portainer GitOps (2026-09-08). Let it sit stable before touching its deploy mechanism again.
- **`portainer-agent`** (quark-vm) and the **final Portainer decommission** — structurally last regardless of pace, since nothing can be safely detached from Portainer's management until every stack it might still reach has already moved.

## Rollback posture per stack

Same posture used throughout the original Portainer GitOps migration: nothing is deleted from Portainer until the Komodo-managed copy is confirmed healthy and serving real traffic. Named volumes are never recreated fresh — always attached via `external: true` to the exact volume Portainer's container was already using, so a bad Komodo deploy loses nothing since the underlying data was never touched by Komodo in the first place. If a stack misbehaves under Komodo, the fallback is simply re-enabling Portainer's GitOps stack for it (not deleted, just no longer the active manager) while the Komodo side is debugged — the two tools never need to run the same stack simultaneously for real traffic, unlike the POC's deliberately-parallel throwaway stacks.

## Komodo Core given a real hostname (2026-09-19, ahead of session 1)

Resolved the "harden Komodo Core" open item below before it became urgent: Core is now reachable at **`https://komodo.local.nelsonhickman.com`** through Traefik (TLS via the same `cloudflare` certresolver every other internal service uses), in addition to — not instead of — its existing Tailscale-IP-bound `100.69.15.50:9120` (kept unchanged, since both Periphery agents' `PERIPHERY_CORE_ADDRESS`/`core_addresses` point at that exact address and didn't need to move).

Mechanics: joined `core` to the external `proxy` network and added the repo's standard Traefik docker-label pattern (same shape as `it-tools`/`homebox`) directly in `/home/nelson/containers/komodo/compose.yml` on nelson-nuc — host-side only, not repo-tracked, consistent with how the rest of the Komodo stack has been handled throughout. Recreated only the `core` service (`docker compose up -d core`); `RestartCount: 0` after. Both Periphery agents (nelson-nuc and quark-vm) logged one expected `Connection refused` / reconnect cycle at the moment `core` restarted, self-healed within 5 seconds — not a real disruption, same pattern already seen during the original Periphery-mount-fix recreate. Confirmed via `curl --resolve komodo.local.nelsonhickman.com:443:192.168.88.101 https://komodo.local.nelsonhickman.com/` → `200`.

**Still needed, not yet done:** a Pi-hole Local DNS Record for `komodo.local.nelsonhickman.com → 192.168.88.101` (nelson-nuc's LAN IP, same address every other `*.local.nelsonhickman.com` entry uses) — Pi-hole isn't part of this repo and wasn't touched from this session; user is adding it directly via the Pi-hole admin UI.

## Session 1 complete (2026-09-19): 6 stateless stacks cut over

Cutover mechanics decided and proven, reusable for every remaining session:

1. **Disable Portainer's polling first, per stack**, via `POST /api/stacks/{id}/git?endpointId=<id>` with the stack's existing `RepositoryReferenceName`/`ConfigFilePath`/`Env`/`SourceID` unchanged and `AutoUpdate: null`. Confirmed via source (`stack_update_git.go`) that this endpoint only updates the stored config and reconciles the polling scheduler — it does **not** pull or redeploy, so it's safe to call against a live stack. The stack's `AutoUpdate.JobID` clears to empty, which is the actual signal polling stopped (the `Interval` field stays populated but is cosmetic once `JobID` is gone). Needed a user-generated Portainer API token for this (Account settings → Access Tokens) since no token existed from earlier work.
2. **Create the Komodo Stack with a name matching the existing Docker Compose project name** (confirmed via `docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project"}}'` before creating each Stack). When the project name matches exactly, Komodo's `docker compose up` recognizes the running container as already satisfying the desired state and **leaves it running untouched** — a true zero-downtime cutover, not a delete/recreate. Confirmed for `it-tools`, `dozzle`, `homebox` (`StartedAt` identical before/after, `RestartCount: 0`). The other 3 (`vert`, both `dozzle-agent` instances) did get a real recreate (minor config drift from what Portainer had last applied) — still clean, just not a no-op.
3. **Same-named resources across hosts need Komodo's `project_name` override**, since Stack *resource* names must be unique per Core but the underlying Docker Compose project name does not need to change. Used this for quark-vm's `dozzle-agent` (Komodo resource named `dozzle-agent-quark-vm`, `project_name: "dozzle-agent"` set explicitly to match its existing container label) so it recreated in place exactly like its nelson-nuc counterpart.

All 6 stacks (`it-tools`, `dozzle`, `dozzle-agent` ×2, `vert`, `homebox`) verified against the same bar as every stack in the original Portainer migration: `RestartCount: 0`, correct `TZ`, `deployed_hash` == `latest_hash` in Komodo, Traefik `200` on the three web-facing ones (`dozzle` restarted once deliberately to force a fresh boot log — confirmed `"clients":2`, both agents connected with no errors).

## Open items to resolve during the migration, not before it

- Final Portainer decommission steps (removing the Portainer container/agent themselves, not just detaching stacks) — deferred to the very end, no need to plan in detail yet.
- The stale `com.docker.compose.project.config_files` label left behind on a no-op cutover (still points at Portainer's old clone path until the next real recreate) — cosmetic only, same behavior already seen on the home-assistant stack-115 reconnect, not worth chasing.
