# Phase 3 - ✅ Infrastructure

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ LOCAL INFRA PROOF GATE REPRODUCED 2026-09-01.** Master Task 2 is ✅. Master
Tasks 23 and 25 are still marked ⬜ in the master plan; treated as done because `7669ec6`
and `bd8b7dd` shipped them. Product-runtime Tasks 1 and 5 through 9 are ✅. Master Task 24
stays ⬜ (FoodSpector shadow). Product-runtime Task 10 stays ⬜. Neither is this local
start-health-restart gate.

## 1 - ✅ Hosted process reports health and readiness

The hosted FastAPI app loads ops, pairing, oauth, approval, and runner-job routers
(`control_plane/app.py:23`). `/health` returns `ok` without touching the database
(`control_plane/ops.py:22`). `/ready` runs `select 1` (`control_plane/ops.py:27`).
Queue, cost, rejection, and circuit endpoints sit next to those
(`tests/test_fault_injection.py`).

## 2 - ✅ Local start binds loopback only

`reviewer start` refuses any host other than `127.0.0.1`
(`runner/cli/service.py:102`). The user unit lives under the home directory, not
`/etc` (`tests/test_user_service.py`). The dashboard factory calls
`require_loopback_bind` (`web/local_auth.py:22`). A non-loopback client gets 403.
Docs, Redoc, and OpenAPI are off (`web/dashboard_api.py:69`). Unauthenticated
`/openapi.json` is not 200.

## 3 - ✅ Local Postgres is loopback, named volume, restart-safe

`LocalVectorStore` binds `127.0.0.1` (`local_store/postgres.py:110`). Compose maps
`127.0.0.1` only and never `0.0.0.0` (`tests/test_runner_compose.py`). The image is
pinned by digest. The process is non-root. Health is false until `start` plus
`migrate` succeed (`tests/test_local_pgvector.py`). A `preserve_data` stop then
start keeps the named volume and the probe row.

## 4 - ✅ Local SQLite and secrets survive without a public port

`open_local_store` writes a `0600` file in a `0700` directory
(`tests/test_local_store.py`). The password for local Postgres is in SecretStore,
not argv and not compose. `reviewer doctor` checks Docker isolation before full
mode (`tests/test_doctor_docker.py`). Missing Docker does not publish a host port
to make up for it.

## 5 - ✅ Release containers are non-root and healthy on paper

CI and release compose pin images, drop to uid 65532, and declare a healthcheck
(`tests/test_release_config.py`). That is config proof. GitHub Actions is not run
tonight because nothing is pushed.

## Design gate - ✅

✅ A clean test environment starts, reports health, restarts without losing the
named volume, and does not bind a public local port.

## Test gate - ✅ reproduced

The proof gate is: a clean test environment starts, reports health, survives a
process restart, and shuts down without losing durable state or exposing a public
local port.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py tests/test_dashboard_api.py::test_health_is_public_on_loopback tests/test_user_service.py tests/test_runner_compose.py tests/test_local_auth.py::test_non_loopback_bind_is_rejected tests/test_fault_injection.py::test_ops_health_readiness_queue_cost_rejection_and_circuit_endpoints tests/test_doctor_docker.py tests/test_local_pgvector.py
...................................................................      [100%]
67 passed, 1 warning in 44.93s
```

`test_named_volume_survives_a_preserve_data_restart` is the restart-and-keep-data
proof. `test_postgres_binds_loopback_only` and `test_non_loopback_bind_is_rejected`
are the no-public-port proof. `test_unauthenticated_docs_and_unknown_paths_are_not_ok`
is the 06:11 FIX.

⚠️ This is not the hosted end-to-end at `https://reviewer.niresh.tech`. Runtime
Task 10 stays morning work. Task 24 (FoodSpector shadow) is not this gate.

## Settled - ✅

- ✅ Local services bind `127.0.0.1` only. A public bind is a failed start, not a
  config warning.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ None for this local infra gate. The public hostname and Traefik router are
  morning work with runtime Task 10.
