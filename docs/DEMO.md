# Demo

| Mark | Means |
|---|---|
| ⬜ | Not done yet |
| ✅ | Runs on this checkout today |
| ❌ | Needs a deployment or a human |
| ❓ | Open |

Walk a signed webhook through to a human decision using commands that run
on this machine. Steps marked ❌ need DNS, Traefik, and a live GitHub App
URL. Those are morning work, not this checkout.

## Screenshots captured today - ✅

Playwright drives the live Task 21 API, then writes:

- `docs/assets/dashboard-desktop.png`
- `docs/assets/dashboard-mobile.png`

Command:

```bash
cd apps/web && bunx playwright test tests/dashboard.spec.ts -g "desktop and mobile screenshots"
```

The test asserts the approval titles that came over the wire, then captures
both viewports. It fails if the dashboard API is down.

## Signed webhook to a queued job - ✅ local

HMAC verification and enqueue are tested without a public hostname.

```bash
flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_webhook.py
```

That suite proves missing headers, bad signatures, draft ignore, enqueue of
an opened pull request, and cancel of a closed one. It does not send a
payload to GitHub.

## Loopback dashboard and a human decision - ✅ local

Start the seeded dashboard API, the Next app, and the loopback onboarding
process the same way Playwright does (`apps/web/playwright.config.ts`).

```bash
cd apps/web && bunx playwright test tests/dashboard.spec.ts
```

That run:

1. Hits `/dashboard/health` on `127.0.0.1:8742`.
2. Opens a local session and shows the paired runner id.
3. Lists jobs the live API returned.
4. Approves `Null check on widget.value` with CSRF.
5. Rejects `Reject this queued finding`.

The dashboard has no webhook route
(`tests/test_dashboard_auth.py::test_dashboard_exposes_no_webhook_route`).
GitHub never posts to the user's machine.

## Hosted worker claiming a real job - ❌ needs deployment

A production webhook URL at `https://reviewer.niresh.tech/api/github/webhook`
does not exist yet. Runtime Task 10 needs:

- DNS A record for `reviewer.niresh.tech` to `76.13.243.12`
- Traefik router for that host
- GitHub App homepage, callback, and webhook URLs pointed at that host

Until then a signed GitHub delivery cannot reach this control plane from
the internet.

## Posting to a real pull request - ❌ needs deployment and a human

`post_review` is tested for stale head and duplicate keys. Posting onto a
FoodSpector PR still needs the deployed App, a paired runner, and a human
approval on a real finding. Task 24 is that shadow run.

## What this demo is not

- It is not a 14-day FoodSpector shadow.
- It does not report precision, recall, or cost per PR. The frozen holdout
  does not exist yet.
- It does not use Redis.

## Settled - ✅

- ✅ Local webhook tests and the Playwright approval path run today.
- ❌ Live GitHub to hosted control plane is blocked on DNS and App URLs.
