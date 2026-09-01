# Phase 4 - ✅ Data Engineering

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ DATA PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 2, 4, 5, 7, 8, and 12
are ✅. Master Tasks 18 and 20 are still marked ⬜ in the master plan; treated as done
because `9685b23` and `0869afd` shipped them. Product-runtime Tasks 1, 1A, 5, 7, and 9
are ✅. Master Task 9 stays ⚠️ because the public holdout is empty. That is an eval
block, not a schema block. Product-runtime Task 10 stays ⬜ and is not this gate.

## 1 - ✅ Hosted migrations are checksummed and forward-only

`migrate` (`db/migrate.py:37`) takes an advisory lock, creates `schema_migrations`,
and applies each file once. A second run compares the stored checksum and continues
(`db/migrate.py:69`). A changed file raises `Migration checksum mismatch`. Applied
files that vanished from disk raise before any new file runs
(`db/migrate.py:62`). There is no down-migration in `migrate()`. Rebase of a
checksum is a separate, explicit command (`db/rebase_migration_checksum.py:42`) and
is not part of normal apply. The suite session already calls `migrate()` from
`tests/conftest.py`.

## 2 - ✅ The hosted schema cannot hold private review data

`assert_no_private_columns` (`control_plane/boundary.py:193`) reads
`information_schema`, not a hand list. Retired tables `findings`, `code_chunks`,
`human_decisions`, and `pull_requests` are gone
(`tests/test_hosted_boundary_enforcement.py`). `HOSTED_EXEMPTIONS` is
`frozenset()`. Event detail lives on the runner after the rescope
(`tests/test_hosted_event_rescope.py`).

## 3 - ✅ Local SQLite is the private half

`_run_migrations` (`local_store/sqlite.py:516`) uses the same checksum skip.
Mismatch raises `LocalStoreCorrupted`. The file is mode `0600` in a `0700`
directory. The local schema has no long-lived secret columns
(`tests/test_local_store.py`). Findings and human decisions live here, not on
Neon.

## 4 - ✅ One lease, skip locked

`claim_review_job` (`jobs/claim_review_job.py:46`) takes the next pending or
expired row with `for update skip locked` (`jobs/claim_review_job.py:59`).
`test_duplicate_claim_does_not_mint_a_second_lease` and
`test_concurrent_claims_of_one_job_exactly_one_wins` prove two callers cannot
own one job. An expired lease is claimable again
(`tests/test_fault_injection.py`).

## 5 - ✅ Tenant isolation is numeric and installation-scoped

`authorize_repository` (`control_plane/repository_policy.py:150`) looks up
`installation_id` and `github_repository_id` together. A rename does not move
data. A transfer does not carry rows. Cross-installation access is denied
(`tests/test_control_plane_identity.py`).

## 6 - ✅ Retention and delete stay on one repository

`uninstall_repository` (`security/retention.py:19`) is the policy. Hosted
deletes go through `purge_hosted_repository` (`control_plane/retention.py:8`).
Every `DELETE` is `installation_id` and `github_repository_id`. Uninstalling
one repository leaves the sibling and the installation
(`tests/test_retention.py`). A sweep that misses its deadline raises
`RetentionSweepTimedOut`.

## Design gate - ✅

✅ Fresh apply and repeat apply are the same `migrate()` path. Repeat is a
checksum skip, not a rewrite. The hosted schema cannot store private review
columns. One job has one lease. Delete is per repository.

## Test gate - ✅ reproduced

The proof gate is: fresh migration, repeat migration, lease concurrency,
tenant isolation, retention, delete-account, and `assert_no_private_columns`.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_migrate.py tests/test_hosted_boundary_enforcement.py tests/test_hosted_event_rescope.py tests/test_jobs.py tests/test_runner_job_protocol.py tests/test_control_plane_identity.py tests/test_retention.py tests/test_local_store.py tests/test_fault_injection.py::test_lease_expiry_makes_the_job_claimable_again
........................................................................ [ 91%]
.......                                                                  [100%]
79 passed, 1 warning in 4.40s
```

`tests/conftest.py` applies hosted migrations before the session. A second
`migrate()` in that session is a checksum skip. `test_assert_no_private_columns_passes_against_the_current_hosted_schema`
reads the live schema. Concurrent claim tests are in
`tests/test_runner_job_protocol.py`.

⚠️ There is no automatic schema down-migration. Rollback of hosted SQL is
"do not apply a changed file" plus an explicit checksum rebase. Binary
rollback is runner update (`tests/test_runner_update.py`), not this gate.

⚠️ Master Task 9's holdout is still empty. This document invents no eval
number.

## Settled - ✅

- ✅ `HOSTED_EXEMPTIONS` stays empty. A new hosted text column needs an
  `ALLOWLIST` reason and a regenerated `docs/DATA_BOUNDARIES.md`.
- ✅ Retention never uses a `WHERE` on `installation_id` alone
  (`tests/test_retention.py`).

## Open Decisions - ❓

- ❓ None for this data gate. Runtime Task 10 remains the hosted end-to-end
  half and is morning work.
