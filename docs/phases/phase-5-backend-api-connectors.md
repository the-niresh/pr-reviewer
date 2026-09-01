# Phase 5 - ✅ Backend, API, and Connectors

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 3, 4, 6 through 8, and 17 are
✅. Master Task 21 is still marked ⬜ in the master plan; treated as done because `e704cd7`
shipped the loopback dashboard API. Product-runtime Tasks 2 through 4 and 8 are ✅.

## 1 - ✅ Signed webhook, then enqueue

HMAC is checked before the delivery is parsed into a job. A replayed
`X-GitHub-Delivery` returns `duplicate` and does not insert a second
`review_jobs` row (`jobs/enqueue_review_job.py:16`, `tests/test_webhook.py`).
The webhook route lives on the hosted FastAPI app only.

## 2 - ✅ Claim, heartbeat, ack

An assigned runner claims a job and receives a lease (`runner_jobs.py:110`). A
second claim does not mint a second lease. Acknowledgement is idempotent
(`tests/test_runner_job_protocol.py`). Queue state stays on `review_jobs`.

## 3 - ✅ Repository-scoped token, then fetch

`issue_job_token` (`token_broker.py:49`) issues a short-lived token only for
the leased job's installation and repository. The runner fetches the PR with
that token. The hosted plane never receives private source.

## 4 - ✅ Stale-safe posting

`post_review` (`github/post_review.py:71`) checks the live head SHA immediately
before submit and keys the GitHub call with an idempotency marker. A retry of
the same key does not post a second review (`tests/test_post_review.py`).

## 5 - ✅ Loopback dashboard, not a second webhook

`create_dashboard_app` (`web/dashboard_api.py:56`) binds `127.0.0.1` only.
Local and hosted I/O are injected. `web/` stays hosted-side in the guard, so
those modules do not import `local_store`, `runner`, `control_plane`, or `db`.
`web/__init__.py` no longer imports the hosted app, so loading the dashboard
modules does not pull Neon. There is no webhook route on this app.

Two identities stay separate: the paired `runner_id` for account data, and a
random local session cookie for localhost access.

## 6 - ✅ Merged trace, not a local-only view

The dashboard trace route calls `reconstruct_trace` (`observability/trace.py:171`)
with both injected halves. A local-only list would silently drop hosted
lifecycle events.

## Design gate - ✅

✅ One signed delivery becomes at most one job. One assigned runner claims it.
One scoped token fetches the PR. One idempotency key posts at most one review.
The installed dashboard is loopback-only and has no inbound GitHub port.

## Test gate - ✅ reproduced

The proof gate is: one signed webhook is acknowledged after durable enqueue,
one assigned runner claims it, one repository-scoped token fetches the PR, and
retries produce no duplicate job or review.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_webhook.py tests/test_jobs.py tests/test_runner_job_protocol.py tests/test_token_broker.py tests/test_post_review.py tests/test_dashboard_auth.py tests/test_dashboard_api.py
........................................................................ [ 88%]
.........                                                                [100%]
81 passed, 1 warning in 4.68s
```

`test_webhook.py` asserts a replayed delivery returns `{"result": "duplicate"}`.
`test_runner_job_protocol.py` asserts a duplicate claim does not mint a second
lease and a duplicate ack is idempotent. `test_post_review.py` covers the
posting key. Dashboard denials (non-loopback, unauthenticated, CSRF, scope)
are in `tests/test_dashboard_auth.py`.

## Settled - ✅

- ✅ Dashboard files live under `web/` at the master-plan paths. I/O is injected.
  That is the same split Task 10 used for `models/` and Task 15 used for
  `notifications/`. No `HOSTED_EXEMPTIONS` entry.
- ✅ The hosted webhook stays on `web/app.py` -> `control_plane.app`. The
  dashboard app is a separate factory.

## Open Decisions - ❓

- ❓ None for this phase. Wiring the dashboard factory into `reviewer start`
  is installer work (master Task 25).
