# Komodo Proof-of-Concept Plan

Status: **in progress** — Core + Mongo + one Periphery agent stood up on nelson-nuc 2026-09-12. See the README's "Migrating off Portainer" section for why this is happening. See "Progress Log" below for what's actually been done against the Steps below.

## Goal

Prove [Komodo](https://github.com/moghtech/komodo) (GPL-3.0) can do this repo's core GitOps loop — a git-tracked compose stack deployed to a named host, auto-redeployed on push — across **two** hosts (nelson-nuc + quark-vm), before committing to migrating anything real off Portainer.

Target stack for the POC: `it-tools` ([`stacks/nelson-nuc/it-tools/docker-compose.yml`](stacks/nelson-nuc/it-tools/docker-compose.yml)). It has no volumes and no secrets — just a single pinned image and Traefik labels on the external `proxy` network — making it the lowest-risk stack in the repo to experiment with, same reason it was a good first stack for the original Portainer GitOps migration (see `CLAUDE.md`, Phase 3).

## Non-goals (explicitly out of scope for this POC)

- **No cutover of the real `it-tools` container or its hostname.** The live, Portainer-managed `it-tools` and `it-tools.local.nelsonhickman.com` are never touched.
- **No secrets or `env_file` handling, no named-volume pinning.** `it-tools` has neither, so this POC only proves the *simple* case. This repo has two known hard patterns that a real migration would also need to validate: absolute-path `env_file`/Docker `secrets:` (see README's Architecture section), and the uptime-kuma/mealie external-volume-pinning trick documented in `CLAUDE.md` (a plain named volume can silently get re-prefixed under a new tool's project name and resolve to an empty volume instead of the real data). Neither is exercised here — see "Follow-up" below.
- **No GitHub webhook wiring.** `CLAUDE.md`'s Phase 4 notes record that Portainer's webhook URL (`*.local.nelsonhickman.com`) is unreachable from GitHub's public delivery servers — LAN-only hostname, no route in. Komodo's webhook receiver would hit the exact same reachability problem if pointed at a LAN-only hostname. Start with polling (the same tradeoff already accepted for all 23 Portainer stacks); webhook-via-the-existing-`cloudflared`-tunnel is a stretch goal only, not a requirement.

## Architecture

- **Komodo Core** — new container on nelson-nuc, its own standalone stack, not yet Traefik-routed (or routed to a throwaway `komodo-poc.local.nelsonhickman.com` for convenience). Kept entirely separate from anything Portainer manages.
- **Periphery agents** — one on nelson-nuc, one on quark-vm. Installing both (not just one) is the part that actually exercises the multi-host hard requirement.
- **Database** — whatever Komodo's docs currently recommend (Mongo by default; FerretDB or Postgres as alternatives if avoiding a new Mongo instance is preferable for a POC-scale deployment).

## Steps

1. Read Komodo's current install docs for the Core + Periphery topology and its auth model (Ed25519 keypairs per its 2026 v2 change) — confirm nothing conflicts with the existing Tailscale/LAN setup between nelson-nuc and quark-vm.
2. Stand up Komodo Core on nelson-nuc as its own compose stack, LAN-only for now.
3. Install Periphery on nelson-nuc, register it with Core.
4. Install Periphery on quark-vm (SSH access already exists — see the Portainer-agent-upgrade entry in `CLAUDE.md`), register it with Core. This is the multi-host proof point.
5. In Komodo, define a Stack resource pointing at this repo (`https://github.com/nph4/Homelab-IaC`, branch `main`, path `stacks/nelson-nuc/it-tools/docker-compose.yml`), but override the deploy identity so it can't collide with the live container: different container name (e.g. `it-tools-komodo-poc`) and a different Traefik router/hostname (e.g. `it-tools-poc.local.nelsonhickman.com`) — the same dual-running pattern this repo already used for the `cloudflared` and `dashy` (`dashy-validate-test`) cutovers. It can still safely join the real external `proxy` network since the container name differs.
6. Deploy to nelson-nuc's Periphery agent. Verify against the same bar every stack in the original Portainer migration was held to: `docker inspect` shows it sourced from the Git clone, correct pinned image tag, `TZ` set, joined to `proxy`, and a `200` through Traefik at the POC hostname.
7. Make a trivial commit on `main` (e.g. a label comment change) and confirm Komodo's poll picks it up and redeploys without manual action — the actual behavior being validated.
8. Repeat a minimal version of steps 5–7 targeting the quark-vm Periphery agent (doesn't need to be `it-tools` specifically — any throwaway stack proves the second host works from the same Core).
9. Judge the GUI against Portainer's for the operations actually used day to day: viewing logs, triggering a redeploy, seeing which commit is currently deployed, spotting drift.

## Success criteria

- Both hosts manageable from a single Komodo Core.
- A git push results in an automatic redeploy, verified via `docker inspect`'s commit hash — not just "the page loads."
- No feature Portainer currently provides for free turns out to require a paid Komodo tier.

## Rollback / cleanup

Trivial by design, since everything here is new and parallel to production: stop/remove the POC container and its Komodo Stack resource, remove both Periphery agents and Komodo Core, delete the POC Traefik hostname. The live `it-tools` and its Portainer entry are never at risk.

## Progress Log

**2026-09-12 — Core, Mongo, and the nelson-nuc Periphery agent stood up (steps 1–3 of "Steps" above).** Deployed as a single compose project at `/home/nelson/containers/komodo/` on nelson-nuc (`compose.yml` + `compose.env`, `.env` symlinked to `compose.env` per Komodo's own template layout) — kept entirely outside this repo and outside Portainer, per the plan's non-goals. Not committed anywhere; this file is the only record of what's running.

Deviations from Komodo's stock template, made before first boot:
- `mongo` image pinned to `mongo:8.0` (template shipped unpinned `mongo:latest`) — matches this repo's own Phase 1 image-pinning convention even though the Komodo stack itself lives outside the repo.
- Core's port publish changed from `9120:9120` (all interfaces) to `100.69.15.50:9120:9120` — bound to nelson-nuc's Tailscale IP only, not LAN-wide. Confirmed reachable over Tailscale from nelson-desktop (`curl http://100.69.15.50:9120/` → `200`), which is a better answer than the plan's "LAN-only for now" assumption in Architecture above — it means quark-vm's Periphery agent (step 4, not yet done) can likely reach Core over Tailscale directly rather than needing real LAN routing between the two hosts.
- `KOMODO_DATABASE_PASSWORD`, `KOMODO_WEBHOOK_SECRET`, `KOMODO_JWT_SECRET`, `KOMODO_INIT_ADMIN_PASSWORD` all regenerated from the template's placeholder values before boot.
- `KOMODO_DISABLE_USER_REGISTRATION` flipped `false` → `true` — closes public signup from the start, the same lesson learned the hard way on `adventurelog`'s insecure defaults (see `CLAUDE.md`).

Verified after boot (`docker compose ps`, `docker compose logs`): all three containers (`komodo-core-1`, `komodo-mongo-1`, `komodo-periphery-1`) up and stable (~2h uptime at check time, no restarts). Core created the init `admin` user and its initial system resources on first boot, serving on `:9120` (SSL disabled — fine for a Tailscale-only-bound POC). Periphery connected to Core over their internal `ws://core:9120` link and logged in as Server **`Local`** (Komodo's `first_server_name` mechanism — no manual server-registration step was needed for the same-host agent). One benign `Connection refused` retry logged at Periphery startup, from Core not yet accepting connections in the first ~10s of the shared compose `up` — self-resolved, not investigated further.

**Not yet done:** no quark-vm Periphery agent (step 4), no Stack resource pointing at this repo's `it-tools` (step 5), no test commit/redeploy cycle (step 7), no GUI evaluation (step 9). This log entry covers infrastructure standup only — the actual GitOps-loop proof (the point of the POC) hasn't started yet.

## Follow-up (separate from this POC)

A second POC stack that exercises an `env_file` secret and/or a named volume, to validate the two hard patterns a real migration actually depends on, before trusting Komodo with anything stateful:
- Absolute-path `env_file` / Docker `secrets:` (see README Architecture section).
- The external-volume-pinning trick used for `uptime-kuma`, `days-since-incident`, and `mealie` (see `CLAUDE.md`) — confirming Komodo either preserves existing volume names the same way, or has an equivalent pin mechanism.
