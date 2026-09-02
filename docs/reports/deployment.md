# Hosted control plane deployment

**Deployed:** 2026-09-02, reviewer.niresh.tech

This records what is actually live, measured from outside the host, and what is not yet
done. Nothing here is asserted from a config file alone.

## What is live

| Property | Evidence |
|---|---|
| DNS | `reviewer.niresh.tech` resolves to `76.13.243.12` on 1.1.1.1 and 8.8.8.8, the host's own IPv4 |
| TLS | Let's Encrypt, `subject=CN = reviewer.niresh.tech`, `notAfter=Dec 1 09:06:56 2026 GMT` |
| HTTP to HTTPS | `http://reviewer.niresh.tech/health` returns `301` to the https URL |
| Liveness | `GET https://reviewer.niresh.tech/health` returns `200` and `{"status":"ok"}` |
| Readiness | `GET https://reviewer.niresh.tech/ready` returns `200`, so the container reaches Neon |
| Containers | api healthy, worker up, ui up, under `compose.release.yml` + `docker-compose.hosted.yml` |
| Schema | 19 of 19 migrations applied to the hosted database |

## Images

Built from the repository Dockerfile, not a placeholder.

- Base images pinned by sha256 digest: `python:3.12-slim`, `oven/bun:1.3.11-slim`,
  `ghcr.io/astral-sh/uv:0.9.30`.
- Python dependencies installed with `uv sync --locked`, so the build matches `uv.lock`.
- api entrypoint `/app/.venv/bin/pr-reviewer-api`, worker entrypoint
  `/app/.venv/bin/pr-reviewer-worker`, ui a real Next.js build.
- All services run as non-root `65532:65532`.
- api image size 89722969 bytes.
- No secret is baked into any layer. Every hosted value is read from the environment at
  run time, and `compose.release.yml` uses `${VAR:?...}` so a missing one fails the run
  rather than starting half-configured.

## Health checks, and why they differ

`/health` deliberately does not touch the database. It answers "is this process alive",
and Docker restarts the container when it fails. If it checked Neon, an outage would
produce a restart loop that fixes nothing.

`/ready` runs `select 1`. It answers "can this serve traffic". Traefik checks it via
`loadbalancer.healthcheck.path: /ready`, so when Neon is unreachable the route is
withdrawn instead of serving requests the application cannot answer.

Two signals, two different responses: restart on liveness, withdraw on readiness.

## Migrations applied during this deployment

Three were pending and are now applied:

- `202609011830_drop_review_jobs_draft.sql`
- `202609020136_review_projection_findings.sql`
- `202609020418_finding_receipts.sql`

The first drops a column. Before applying it, `review_jobs` held 40 rows and
`select draft, count(*) group by draft` returned a single group, `(None, 40)`, so the
column carried no data and had no writer in `src/`.

## Routing

Both surfaces are routed on the same host, split by explicit Traefik priority rather
than rule-length defaults: `reviewer-api` (priority 100) takes `/api`, `/health` and
`/ready`; `reviewer-ui` (priority 1) takes everything else. Measured from outside:
`/` 200 serving the landing page, `/docs` 200, `/health` 200, `/ready` 200, and
`/api/reviews` 401 rather than data, which is the fail-closed default.

## Not done, and why

- **GitHub App 4771544 still points at the apex.** Homepage, callback
  (`/api/auth/github/callback`) and webhook (`/api/github/webhook`) must move to
  `https://reviewer.niresh.tech`. Until that is changed in GitHub, no webhook reaches
  this deployment and the OAuth callback does not return here. This needs a human with
  access to the App settings.
- **No webhook delivery has been observed.** This report does not claim one. The URL is
  stable and HTTPS, which is what the phase 19 step asks for, but proof of a real
  delivery belongs to the shadow run.

## Rollback

```sh
docker compose -f compose.release.yml -f docker-compose.hosted.yml down
```

Traefik drops the router because the Docker provider watches labels. Leave GitHub App
4771544 on the apex until the subdomain is gone, and remove the `reviewer` A record last.
Do not change Traefik's own command or cert resolver as part of a rollback.
