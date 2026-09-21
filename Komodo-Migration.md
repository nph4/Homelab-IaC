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
5. **Remaining quark-vm stacks:** `crashplan`, `paperless`. (2 stacks.) `jellyfin` was originally planned here as an in-place adoption on nelson-nuc, but is now **superseded**: it moves straight from Portainer to a new dedicated GPU host — see "Planned: dedicated GPU host for Jellyfin" below. It stays on Portainer/nelson-nuc until that host is ready.

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

## Planned: dedicated GPU host for Jellyfin (decided 2026-09-21, not started)

Jellyfin's transcoding on nelson-nuc (HD Graphics 620, VAAPI/QSV) has been the recurring pain point. New hardware bought to fix it: **Dell OptiPlex 7040 SFF** (i5-6500, 16GB RAM, 500GB SATA SSD) + **NVIDIA Quadro P1000** + a **2.5GbE NIC** (eBay listing; chipset not yet confirmed). This is a new Docker host, onboarded to Komodo from day one — greenfield, so no Portainer cutover for the host itself. Timing is open; it competes with the routine sessions above for the same biweekly 2 hours, so slot it in when the hardware is ready rather than forcing it.

### Decision: Ubuntu LTS + Docker + Komodo Periphery (same model as nelson-nuc)

Options considered and why this one won:
- **Ubuntu + Jellyfin as a native app** — rejected. Docker is namespaces/cgroups, not virtualization, so a container transcodes at native speed; going native gains almost nothing and makes the host invisible to this repo (the failure mode most of this file's history is about).
- **Proxmox + LXC, Jellyfin native** — rejected for now. Real upside is snapshots (would have simplified the Home Assistant upgrade backups), but GPU passthrough into an unprivileged LXC needs host/guest NVIDIA driver versions kept in lockstep with manual cgroup rules, and a whole second stack (plus Terraform/Ansible) to keep IaC-clean, on a single node with one SSD — most of Proxmox's payoff (ZFS mirror, clustering, HA) is unavailable.
- **Proxmox + one Ubuntu VM with the P1000 passed through (VFIO)** — the best version of "I want Proxmox", but IOMMU grouping on the Q170 chipset may need the ACS override patch, and the GPU becomes exclusive to that VM. Same second-stack cost.
- **Deciding factor is reversibility, not performance** — NVENC is fixed-function silicon, so every option transcodes identically. With Ubuntu + Docker the host is disposable (everything lives in the repo + Komodo), so adopting Proxmox later costs an afternoon. **Revisit Proxmox only when a real service needs something Docker can't do**; Ubuntu + KVM/libvirt covers a one-off VM without it.

### Hardware facts to keep in mind

- 7040 SFF has **one PCIe x16 + one x4, both half-height**, a **180W PSU**, 4 DIMM slots (64GB max), one M.2 2280 slot. P1000 (47W, no aux power, low-profile) fits the budget; the NIC takes the other slot and **needs a low-profile bracket** — confirm the listing includes one.
- **Confirm the NIC chipset** (Realtek RTL8125 vs Intel I226-V). RTL8125 may need the vendor `r8125` DKMS driver on some kernels; I226-V works out of the box.
- **2.5G only helps on the NAS hop** (`/mnt/nas`) — verify the switch port and NAS side are actually 2.5G, or the card changes nothing.
- **P1000 (Pascal) has no AV1 encode *and* no AV1 decode.** Keep `AllowAv1Encoding` **false** (see memory: HD 620 note applies here too); AV1 sources will software-decode on the i5-6500 — fine at 1080p, painful at 4K. If 4K AV1 becomes common, that's the next hardware trigger (Ampere+ GPU), not a config problem.
- Once a dGPU is installed the BIOS may disable the iGPU; not worth fighting for — Skylake QuickSync is what we're leaving behind.

### Plan (order matters; nothing on nelson-nuc is touched until the last step)

1. **Prep the box.** Update the Dell BIOS. Confirm the NIC chipset/bracket and that the switch/NAS path is 2.5G. Install current Ubuntu LTS, create user `nelson` with **UID/GID 1000** (matches Jellyfin's `PUID`/`PGID` and the `/config` ownership being copied), enable SSH key auth.
2. **Base host state** (all host-side, invisible to this repo — write each one down in this file when done, same as the prune crontabs): Docker Engine + **compose v2 plugin** (quark-vm only has the old standalone binary), Tailscale, the `/mnt/nas` mount in `fstab` (copy mount type/options from nelson-nuc), the external `proxy` Docker network, and `/home/nelson/containers/`.
3. **NVIDIA driver + container toolkit.** Install via `ubuntu-drivers`, preferring Canonical's **prebuilt signed kernel-module packages** over DKMS (avoids rebuild-on-kernel-update breakage and Secure Boot MOK enrollment). **Check at install time that the current driver branch still supports Pascal** — Pascal was slated to drop out after the 580 series. Then `nvidia-container-toolkit` + `nvidia-ctk runtime configure --runtime=docker`. Verify with `nvidia-smi` on the host and in a throwaway `nvidia/cuda` container.
4. **Pin the driver.** `apt-mark hold` the NVIDIA driver/utils packages and exclude them from unattended-upgrades. A driver upgrade without a reboot yields `Failed to initialize NVML: Driver/library version mismatch` and every transcode dies until reboot. Upgrade deliberately, reboot right after.
5. **Komodo Periphery on the new host**, using the outbound-only privileged-onboarding-key pattern from the PoC (no `address`, no inbound port). Root dir must be under the user's home if there's no passwordless sudo. Add the read-only `/home/nelson/containers` mount only if a stack there needs an absolute-path `env_file` (Jellyfin's compose doesn't).
6. **Repo side:** new `stacks/<new-hostname>/jellyfin/docker-compose.yml`. Changes vs. the nelson-nuc file: drop `devices: /dev/dri` and `group_add: "109"`, add the NVIDIA device reservation, add the transcode temp dir as tmpfs, publish 8096 on the LAN/Tailscale address so Traefik can reach it (see step 8), keep the 1900/7359 UDP discovery ports. Add the new host to the README layout/services tables. (Compose file not written yet — deliberately deferred.)
7. **Copy the Jellyfin config — the landmine-shaped step.** A fresh `/config` means a **new `ServerId`** and every user loses watch history and library state. Stop the container on nelson-nuc, `rsync -a` `/home/nelson/containers/Jellyfin/config` to the new host (preserving ownership), start Jellyfin on the new host, and confirm the **`ServerId` matches** the old one (same check used in the original Phase 3 migration). Leave the nelson-nuc config directory in place for a good while as the rollback.
8. **Routing — hidden cost.** Traefik on nelson-nuc discovers services via the *local* Docker socket, so the new host's container **can't use Docker labels**. It needs a **static route in `config.yml`** pointing at the new host's address (same pattern `unifi`, `crashplan` and `paperless` already use), which means touching Traefik's host-synced `config.yml` (repo copy + manual sync to `/home/nelson/containers/traefik/data/`, per the traefik gotcha above). Pi-hole needs no change — `jellyfin.local.nelsonhickman.com` still resolves to nelson-nuc's Traefik. Do this as the cutover switch, after the new instance is verified on its own IP.
9. **Switch acceleration inside Jellyfin** (UI setting stored in `/config`, not compose): VAAPI → **NVENC**, enable HEVC/H.264 (+10-bit) decode, enable tone-mapping, leave AV1 encode off, point the transcode path at the tmpfs mount. Test a forced HDR→SDR transcode and a couple of concurrent 1080p streams; watch `nvidia-smi` for the `ffmpeg` process to confirm it's actually on the GPU.
10. **Cutover + Portainer cleanup.** Disable Portainer's polling on the nelson-nuc `jellyfin` stack (same `AutoUpdate: null` call as session 1), stop that container, flip the static route in `config.yml`, verify through Traefik (`302` to `/web/`), then remove the Portainer stack. **This replaces the in-place Komodo adoption of `jellyfin` in session 5** — it moves straight from Portainer to Komodo *on the new host*, skipping a pointless intermediate move on nelson-nuc.
11. **Afterward:** record host-side state in `CLAUDE.md` (fstab, NVIDIA hold, driver branch, NIC driver), update the README service inventory, and consider whether any other GPU-friendly service should share the P1000 while Jellyfin is idle.

### Open questions

- Hostname for the new box (and its Tailscale name) — undecided.
- NIC chipset and low-profile bracket — unconfirmed (eBay listing wasn't readable).
- 7040 SFF fan/thermals under sustained transcode with the P1000 — unverified, watch GPU/CPU temps in the first week.
- Whether the same host should later also take over other media-adjacent stacks (`calibre-web`, etc.) — out of scope for now; nothing decided.

## Open items to resolve during the migration, not before it

- Final Portainer decommission steps (removing the Portainer container/agent themselves, not just detaching stacks) — deferred to the very end, no need to plan in detail yet.
- The stale `com.docker.compose.project.config_files` label left behind on a no-op cutover (still points at Portainer's old clone path until the next real recreate) — cosmetic only, same behavior already seen on the home-assistant stack-115 reconnect, not worth chasing.
