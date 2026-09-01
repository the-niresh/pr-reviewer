Nothing in this file is applied. DNS, Traefik, Compose, and GitHub App 4771544 are unchanged.

# reviewer.niresh.tech deployment runbook

This is preparation only. No DNS record is created. No container is started.
No Traefik command is changed. No GitHub App setting is edited.

## DNS A record (not created)

Name: `reviewer.niresh.tech`
Type: A
Value: `76.13.243.12`

The apex `niresh.tech` stays as it is. This is a new subdomain record.

## Traefik v2.11 (not loaded, not restarted)

This VPS already runs `traefik:v2.11` with:

- Docker provider, `exposedbydefault=false`
- entrypoints `web` (80) and `websecure` (443)
- HTTP to HTTPS redirect
- cert resolver name `letsencrypt`
- Docker network `n8n-mkvx_proxy`

File-provider YAML: `deploy/traefik/reviewer.yml` (router `reviewer`, service
`reviewer`, Host `reviewer.niresh.tech`, backend `http://api:8000`).
This Traefik process has no file provider, so that YAML is not live.

Apply path when a human chooses to deploy: merge
`docker-compose.hosted.yml` onto `compose.release.yml`. Labels enable the
same router and service on the `api` container. That merge is not run here.

Offline check that was run:

```sh
docker compose -f compose.release.yml -f docker-compose.hosted.yml config
```

## GitHub App 4771544 URLs (not edited)

The App is still on the apex. Change these three from `niresh.tech` to the
subdomain when DNS and Traefik are actually live:

- Homepage: `https://reviewer.niresh.tech`
- Callback: `https://reviewer.niresh.tech/api/auth/github/callback`
- Webhook: `https://reviewer.niresh.tech/api/github/webhook`

Callback path is `oauth_api.CALLBACK_PATH`. Webhook path is
`POST /api/github/webhook` on the control plane.

## Rollback (not performed)

1. Stop the hosted overlay: `docker compose -f compose.release.yml -f docker-compose.hosted.yml down`.
   Traefik drops the router because the Docker provider watches labels.
2. Leave GitHub App 4771544 on the apex until the subdomain is gone, or point
   the three URLs back to `niresh.tech`.
3. Remove the `reviewer.niresh.tech` A record if it was added.

Do not change Traefik's own command or cert resolver as part of rollback.

## What this runbook does not do

- Task 24 FoodSpector shadow
- Runtime Task 10 live webhook proof
- Any precision, recall, latency, or cost number
