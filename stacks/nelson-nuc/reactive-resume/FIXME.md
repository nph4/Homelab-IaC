# Reactive Resume — Resolved Issues & Notes

## Issue 1: 404 after upgrading to v5.0.11 (RESOLVED)

Reactive Resume v5.0.11 renamed several required environment variables. The container booted but failed env validation on every SSR request.

| Old name | New name |
|---|---|
| `PUBLIC_URL` | `APP_URL` |
| `CHROME_URL` | `PRINTER_ENDPOINT` |
| `ACCESS_TOKEN_SECRET` + `REFRESH_TOKEN_SECRET` | `AUTH_SECRET` |

**Fix applied:** Updated `docker-compose.yml` with new variable names. Applied in Portainer's compose editor and redeployed.

---

## Issue 2: Container "unhealthy" → Traefik drops route → 404 (RESOLVED)

**Root cause (two-part):**

1. Reactive Resume v5 checks Browserless health via HTTP. Browserless v2 requires the token for all endpoints — including health checks — when `TOKEN` is set. RR's health checker doesn't pass the token, so Browserless returns `"Bad or missing token"` (plain text). RR can't JSON-parse this → printer shows `unhealthy` in `/api/health`.

2. The reactive-resume Docker image has a built-in `HEALTHCHECK` that calls `/api/health`. When printer is unhealthy, `/api/health` returns non-200. Docker marks the container `unhealthy`. **Traefik v3 removes routes for Docker containers with a failing healthcheck** (behavior change from v2). Result: 404 for all requests.

**Fix applied:** Removed `TOKEN` from the `chrome` service and `CHROME_TOKEN` from the `app` service. Since `chrome` is only on the `internal` network (never exposed externally), no token is needed. Without a token set, Browserless accepts health check requests unauthenticated → printer shows `healthy` → Docker marks container `healthy` → Traefik registers the route.

**Changes in git:** `TOKEN` and `CHROME_TOKEN` removed from `docker-compose.yml`. Apply same change in Portainer's compose editor, then redeploy the full stack.

---

## Issue 3: `${VAR}` substitution blocked Repository-mode GitOps (RESOLVED)

`docker-compose.yml` used Compose `${VAR}` substitution for `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, `AUTH_SECRET`, `MAIL_FROM`, and values composed from them (`DATABASE_URL` embedding the Postgres password; `STORAGE_ACCESS_KEY`/`STORAGE_SECRET_KEY` reusing the MinIO credentials under different names). That requires a `stack.env` committed to the repo for Repository-mode GitOps — not viable in a public repo (same issue as traefik's dashboard credentials).

**Fix applied:** Consolidated onto a single shared `env_file: /home/nelson/containers/reactive-resume/.env`, same pattern as adventurelog. Since `env_file` can't do string interpolation, the composed values are written out literally in the `.env` (the Postgres password appears both standalone and inside `DATABASE_URL`; the MinIO credentials appear both standalone and duplicated as `STORAGE_ACCESS_KEY`/`STORAGE_SECRET_KEY`). `docker-compose.yml`'s `environment:` blocks now hold only static, non-secret config.

**Host state confirmed while fixing this:** the currently running stack (deployed from `/home/nelson/stacks/reactive-resume/`, not yet GitOps) had a stale on-disk `.env` still using the old `CHROME_TOKEN`/`ACCESS_TOKEN_SECRET`/`REFRESH_TOKEN_SECRET` names from before Issues 1–2 were fixed — `AUTH_SECRET` and `MAIL_FROM` were actually coming from Portainer's env var UI override, not that file. Pulled the real live values via `docker inspect` on the running containers rather than trusting the stale file, and wrote the new `/home/nelson/containers/reactive-resume/.env` from those.

## Future

Redeploy via Portainer's local editor with the updated compose + new `.env` path, confirm the app still works end-to-end (login, resume editor, PDF export via chrome/browserless, storage via minio), then connect this stack to Portainer GitOps (it's already in the Phase 3 list in CLAUDE.md) so future compose changes come from the git repo automatically.
