# Komodo Migration Plan

Status: **planning complete, session 1 not yet started (2026-09-19).** This is the actual migration off Portainer, distinct from the completed proof-of-concept — see [`Komodo-PoC.md`](Komodo-PoC.md) for what was validated (both hard patterns, GUI usability, no paid tier) before this plan was written. See the README's "Migrating off Portainer" section for the high-level why.

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

## Open items to resolve during the migration, not before it

- Exact per-stack cutover mechanics (detach-then-deploy vs. stop-Portainer-then-deploy-Komodo) — likely decided by trying it once on the first `it-tools` real-traffic stack in session 1 and reusing whatever works cleanly.
- Whether to harden Komodo Core itself (TLS, Traefik-routed hostname instead of Tailscale-IP-only) before real production traffic depends on it — currently fine for a PoC, worth revisiting once it's managing 20+ real services.
- Final Portainer decommission steps (removing the Portainer container/agent themselves, not just detaching stacks) — deferred to the very end, no need to plan in detail yet.
