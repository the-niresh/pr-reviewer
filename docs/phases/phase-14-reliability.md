# Phase 14 - ✅ Reliability

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ FAULT-INJECTION PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 4, 7, 8, 10,
and 17 are ✅. Master Tasks 18 and 23 are still marked ⬜ in the master plan; treated as
done because `9685b23` and `7669ec6` shipped them. Product-runtime Tasks 3, 4, 6, and 9
are ✅. Product-runtime Task 10 stays ⬜. That is the hosted end-to-end, not this fault
gate.

## 1 - ✅ Retry has a hard deadline

`run_with_retry` (`reliability/retry.py:54`) sleeps through an injected clock. If
the next wait would pass the deadline it raises `RetryDeadlineExceeded`
(`reliability/retry.py:13`). GitHub timeouts retry until that deadline. Rate
limits use `Retry-After`, not a guessed exponential
(`reliability/retry.py:17`). Neon interruptions are retryable
(`reliability/retry.py:47`).

## 2 - ✅ Unknown circuit is open

`decide_unreadable_circuit` (`reliability/circuit.py:39`) returns `open`. A missing
row is closed so the first call can run (`tests/test_fault_injection.py`). Half-open
uses `probe_after_monotonic`. There is no poll loop. The reliability package
imports neither Neon nor SQLite.

## 3 - ✅ Crash, dead job, lease, duplicate

`fail_review_job` (`jobs/fail_review_job.py:20`) takes a closed-set
`ReviewJobErrorClass`. After max attempts the job is dead
(`jobs/requeue_review_job.py:8`). Manual requeue is the only return to pending.
An expired lease is claimable again. A replayed delivery does not insert a
second job.

## 4 - ✅ Stale head and duplicate post

`post_review` (`github/post_review.py:71`) checks the live head SHA before submit
and keys the GitHub call with an idempotency marker
(`github/post_review.py:67`). A stale SHA does not post. The same key does not
post twice.

## 5 - ✅ Lost ack and control-plane outage

Completing a job during a network outage writes a pending acknowledgement
(`tests/test_runner_daemon.py`). Offline after local completion keeps the result
(`tests/test_runner_offline.py`). An invalid or expired ack reclaims instead of
retrying the same lease. Duplicate acknowledgement is idempotent. Jobs queued
while the runner is offline are claimed on reconnect.

## Design gate - ✅

✅ Expected GitHub, model, database, worker, and network failures have bounded
outcomes. Duplicate delivery and duplicate post have no second effect.

## Test gate - ✅ reproduced

The proof gate is: fault injection covers GitHub retry, model timeout, database
disconnect, runner crash, control-plane outage, lost acknowledgement, stale
head, and duplicate delivery without duplicate effects.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_fault_injection.py tests/test_post_review.py::test_stale_head_sha_does_not_post tests/test_runner_offline.py tests/test_runner_job_protocol.py::test_jobs_queue_while_the_runner_is_offline_then_claim_on_reconnect tests/test_runner_job_protocol.py::test_stale_head_sha_is_superseded_and_not_claimed tests/test_runner_job_protocol.py::test_duplicate_acknowledgement_is_idempotent tests/test_runner_daemon.py::test_completing_a_job_during_a_network_outage_persists_a_pending_acknowledgement
.................................                                        [100%]
33 passed, 1 warning in 3.14s
```

`test_unauthenticated_docs_and_unknown_paths_are_not_ok` is the 06:11 FIX.

⚠️ This is not the hosted end-to-end at `https://reviewer.niresh.tech`. Runtime
Task 10 stays morning work.

## Settled - ✅

- ✅ `reliability/` is shared. It does not import stores.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ None for this fault gate. Public deploy remains runtime Task 10.
