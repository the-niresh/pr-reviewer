# Phase 17 - ✅ Frontend Engineering

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 21, 22, and 25 are treated as
done at `bd8b7dd` (Task 21 shipped in `e704cd7`, Task 22 in `5a95d15`). Product-runtime
Task 8 is ✅.

## 1 - ✅ Loopback session, deny by default

`create_dashboard_app` (`web/dashboard_api.py:56`) binds `127.0.0.1` only. Health and
session are public. Every other path needs a valid session. Docs, Redoc, and OpenAPI
are disabled. An unauthenticated loopback GET of `/openapi.json` or an unknown path is
not 200 (`tests/test_dashboard_auth.py`).

## 2 - ✅ Onboarding on the existing Bun app

Runtime Task 8 already owned `apps/web`. Onboarding still pairs, stores a model key
without echoing it, and shows doctor and runtime mode from the live local API
(`apps/web/tests/onboarding.spec.ts`).

## 3 - ✅ Approval queue and job scope

`/dashboard` loads `/dashboard/approvals` and `/dashboard/jobs` after the session
cookie exists (`apps/web/src/app/dashboard/page.tsx`). Approve and reject POST the
live decision. Jobs outside the paired runner or repository set never appear.

## 4 - ✅ Finding, context, trace, cost, evals, connectors

The job page reads findings, events, costs, and the merged trace from the Task 21
API (`apps/web/src/app/dashboard/jobs/[jobId]/page.tsx`). Evals and connectors are
separate routes. The trace is `reconstruct_trace`, not a local-only list.

## 5 - ✅ Loading, empty, partial failure, stale, permission denied

Those five states are asserted against live or intercepted Task 21 responses in
`apps/web/tests/dashboard.spec.ts`. A title is a disclosure surface: the dashboard
title is `Review dashboard`, not a security string.

## 6 - ✅ Setup without hosted-plane prompts

`reviewer setup` (`cli/main.py:21`) reads the model key with hidden input. The
install script copies a release archive only after `sha256sum -c`. Uninstall keeps
data unless both delete flags are set. Doctor reports control-plane reachability,
pairing, keys, ports, disk, and Docker (`cli/doctor.py:27`).

## Design gate - ✅

✅ The installed UI talks to a loopback API. Unknown paths are closed. Setup never
asks for a hosted credential. Playwright would fail if the Task 21 API were down.

## Test gate - ✅ reproduced

The proof gate is: Playwright covers onboarding, review inspection, approval,
rejection, private security routing, trace display, cost display, narrow screens,
and localhost security checks.

Command, run 2026-09-01 against this checkout:

```text
$ cd apps/web && bunx playwright test --reporter=line
  17 passed (23.7s)
```

`tests/test_dashboard_auth.py` asserts unauthenticated `/openapi.json` and
`/missing` are not 200. `tests/test_installer.py` installs a checksummed blob in a
non-root busybox container.

## Settled - ✅

- ✅ Dashboard files stay under `web/` with injected I/O. No `HOSTED_EXEMPTIONS`.
- ✅ `reviewer doctor` remains the Docker probe in `runner/cli/doctor.py`. The
  expanded install-time checks live in `cli/doctor.py`.

## Open Decisions - ❓

- ❓ None for this phase. Wiring `create_dashboard_app` into `reviewer start` is
  already installer work and can stay next to the user-service unit.
