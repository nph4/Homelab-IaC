# Reactive Resume 404 Fix — In Progress

**Date:** 2026-06-28  
**Claude session ID:** not available (Claude Code does not expose session IDs)

## Root Cause

Reactive Resume v5.0.11 renamed several required environment variables. The container boots and serves requests but fails env validation on every SSR request, returning 500 → Traefik sees no valid response → 404 to browser.

Renamed variables:

| Old name (still in Portainer's compose) | New name (required by v5.0.11) |
|---|---|
| `PUBLIC_URL` | `APP_URL` |
| `CHROME_URL` | `PRINTER_ENDPOINT` |
| `ACCESS_TOKEN_SECRET` + `REFRESH_TOKEN_SECRET` | `AUTH_SECRET` (single secret) |

## What's Been Done

1. Updated `docker-compose.yml` in the git repo with the new variable names and removed the two old token secrets.
2. Added `AUTH_SECRET` to Portainer's environment variables UI (value is already there).

## What Still Needs to Be Done

**Portainer is not connected to GitOps for this stack yet**, so the git repo changes haven't been applied. The stack is still using Portainer's internal compose copy with the old variable names.

### Step 1 — Update Portainer's compose editor

In Portainer → Stacks → reactive-resume → Editor, replace the `app` service `environment:` block with:

```yaml
      APP_URL: https://resume.local.nelsonhickman.com
      STORAGE_URL: https://resume-storage.local.nelsonhickman.com/default

      CHROME_TOKEN: ${CHROME_TOKEN}
      PRINTER_ENDPOINT: ws://chrome:3000

      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/postgres

      AUTH_SECRET: ${AUTH_SECRET}

      MAIL_FROM: ${MAIL_FROM}
      # SMTP_URL: ${SMTP_URL}

      STORAGE_ENDPOINT: minio
      STORAGE_PORT: 9000
      STORAGE_REGION: us-east-1
      STORAGE_BUCKET: default
      STORAGE_ACCESS_KEY: ${MINIO_ROOT_USER}
      STORAGE_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
      STORAGE_USE_SSL: "false"
      STORAGE_SKIP_BUCKET_CHECK: "false"
```

### Step 2 — Deploy

Click Deploy in Portainer. This will apply both the compose change and the `AUTH_SECRET` env var (env var changes also don't take effect until redeployment).

### Step 3 — Verify

```bash
docker logs reactive-resume 2>&1 | grep -A 20 "Invalid environment" | head -25
# Should return nothing if fixed

docker ps | grep reactive-resume
# app container should show (healthy)
```

Then visit https://resume.local.nelsonhickman.com — should load the login page.

## Future

Once working, connect this stack to Portainer GitOps (it's already in the Phase 3 list in CLAUDE.md) so future compose changes come from the git repo automatically.
