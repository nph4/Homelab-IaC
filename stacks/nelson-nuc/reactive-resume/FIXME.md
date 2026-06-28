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

## Future

Connect this stack to Portainer GitOps (it's already in the Phase 3 list in CLAUDE.md) so future compose changes come from the git repo automatically.
