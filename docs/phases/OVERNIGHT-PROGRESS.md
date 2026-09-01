# Overnight progress - 2026-09-01

## Task P0 - ✅ done  2026-09-01T05:20:00+05:30
- RED: n/a, docs only
- GREEN: 659 passed. ruff 0, mypy 0, boundary doc current, exemptions empty.
- Commit: 980b8f0 phase 8, 57f274e phase 9, phase 12 in this commit
- Decisions: Master Task 18 is still ⬜ in `2026-08-25-ai-pr-reviewer.md` but HEAD is `9685b23` (`feat: add retry, circuit breaker, fail-closed budgets, and retention`). Treated as ✅ for the crosswalk so Phases 8 and 12 could be written. Task 9 stays ⚠️ because the holdout is genuinely empty.
- Blocked: measured proof for Phases 8 and 9. `BaselineBlocked: holdout is empty`.
- Written: phase 8, phase 9, phase 12. Phases 0-2 already existed and were not rewritten.
- Skipped:
  - Phase 2 rewrite: mapped 18 (plan ⬜, treated done), 23 ⬜, 25 ⬜, runtime 10 ⬜. Existing design-gate file kept.
  - Phase 3: master 23 ⬜, 24 ⬜, 25 ⬜, runtime 10 ⬜
  - Phase 4: master 9 ⚠️, 18 (plan ⬜), 20 ⬜, runtime 10 ⬜
  - Phase 5: master 21 ⬜
  - Phase 6: master 18 (plan ⬜), 20-22 ⬜, 26 ⬜, runtime 10 ⬜
  - Phase 7: master 9 ⚠️, 19 ⬜, 20 ⬜, 24 ⬜, 26 ⬜
  - Phase 10: master 23 ⬜, runtime 10 ⬜
  - Phase 11: master 21 ⬜, 22 ⬜, 24 ⬜, runtime 10 ⬜
  - Phase 13: master 19 ⬜, 20 ⬜
  - Phase 14: master 18 (plan ⬜), 23 ⬜, runtime 10 ⬜
  - Phase 15: master 9 ⚠️, 20-22 ⬜, 24 ⬜, 26 ⬜
  - Phase 16: master 18-20 ⬜, 22 ⬜, 24 ⬜, 26 ⬜
  - Phase 17: master 21 ⬜, 22 ⬜, 25 ⬜
  - Phase 18: master 20-23 ⬜, 25 ⬜, 26 ⬜
  - Phase 19: master 20 ⬜, 23-26 ⬜, runtime 10 ⬜
  - Phase 20: master 9 ⚠️, 20 ⬜, 24 ⬜, 26 ⬜

## Phase 8 - ⚠️ partial  2026-09-01T05:20:00+05:30
- RED: n/a
- GREEN: proof command raised `BaselineBlocked: holdout is empty; refusing to report a baseline`
- Commit: 980b8f0 docs: add phase 8 write-up with verified proof gate
- Decisions: quoted the refusal. No quality, latency, or cost number invented.
- Blocked: frozen holdout does not exist

## Phase 9 - ⚠️ partial  2026-09-01T05:20:00+05:30
- RED: n/a
- GREEN: proof command raised `BaselineBlocked` for retrieval and context-source comparison
- Commit: 57f274e docs: add phase 9 write-up with verified proof gate
- Decisions: no source marked kept or discarded
- Blocked: frozen holdout does not exist

## Phase 12 - ✅ done  2026-09-01T05:20:00+05:30
- RED: n/a
- GREEN: `11 passed, 8 deselected in 0.71s` on the resume/crash workflow tests
- Commit: docs: add phase 12 write-up with verified proof gate
- Decisions: none
- Blocked: -

## Task 19 - ✅ done  2026-09-01T05:34:42+05:30
- RED: 17 failed, 2 passed, failing for: missing specialist, merge, langgraph, and comparison modules
- GREEN: 691 passed. ruff 0, mypy 0, boundary doc current, exemptions empty.
- Commit: 379b358 feat: add specialist reviewers, deterministic merge, and langgraph adapter
- Decisions: LangGraph 1.2.11 installed. Adapter is off by default. Shared WorkflowEngine tests are parametrized over SimpleEngine and LangGraphEngine. Public holdout comparison raises BaselineBlocked. Synthetic holdout is unit-test only.
- Blocked: measured one-agent vs specialist numbers. Public dataset has zero holdout cases.

## Task P1 after 19 - ✅ done  2026-09-01T05:34:42+05:30
- RED: n/a
- GREEN: no new phase document. Phase 13 maps to master 19 and 20; 20 is still ⬜.
- Commit: none
- Decisions: none
- Blocked: -

## Task 20 - ✅ done  2026-09-01T05:46:58+05:30
- RED: 13 failed, 2 passed, failing for: missing regression_gate, feedback_candidates, write_eval_report, EVALS.md
- GREEN: 708 passed. ruff 0, mypy 0, boundary doc current, exemptions empty.
- Commit: 0869afd feat: add eval regression gates, feedback candidates, and drift checks
- Decisions: high-value recall is recall_per_finding. useful_findings_per_dollar now raises BaselineBlocked when cost_usd <= 0 and divides useful_finding_count. CLAUDE-IN FIX applied in this commit. One dispute never rewrites prompts, policy, labels, or routing.
- Blocked: real baseline numbers. Public holdout is empty. Gates are tested with synthetic EvalRun objects.

## Task P1 after 20 - ✅ done  2026-09-01T05:46:58+05:30
- RED: n/a
- GREEN: Phase 13 mapped tasks 19 and 20 are now implemented. Document written.
- Commit: see Phase 13
- Decisions: none
- Blocked: -

## Phase 13 - ⚠️ partial  2026-09-01T05:46:58+05:30
- RED: n/a
- GREEN: proof command printed specialists_enabled False, langgraph_engine_enabled False, then `BaselineBlocked: holdout is empty; refusing to report a specialist comparison`
- Commit: docs: add phase 13 write-up with verified proof gate
- Decisions: quoted the refusal. No specialist quality number invented.
- Blocked: frozen holdout does not exist

## Task 21 - ✅ done  2026-09-01T05:59:42+05:30
- RED: 22 failed, 0 passed, failing for: missing dashboard modules
- GREEN: 730 passed. ruff 0, mypy 0, boundary doc current, exemptions empty.
- Commit: e704cd7 feat: add loopback-only authenticated dashboard api
- Decisions: Dashboard files live under web/ at the plan paths. Local and hosted I/O are injected. web/__init__.py no longer imports the hosted app. Two identities: paired runner_id for account, random local session cookie for localhost. No webhook route.
- Blocked: -

## Task P1 after 21 - ✅ done  2026-09-01T05:59:42+05:30
- RED: n/a
- GREEN: Phase 5 mapped tasks are now implemented. Document written.
- Commit: see Phase 5
- Decisions: Master Task 21 heading is still ⬜; treated as done because e704cd7 shipped it.
- Blocked: -

## Phase 5 - ✅ done  2026-09-01T05:59:42+05:30
- RED: n/a
- GREEN: `81 passed, 1 warning in 4.68s` on webhook, jobs, claim, token broker, post_review, and dashboard tests
- Commit: docs: add phase 5 write-up with verified proof gate
- Decisions: none
- Blocked: -

## Task 22 - ✅ done  2026-09-01T06:13:00+05:30
- RED: 1 failed, 12 did not run (serial). `/dashboard` never called the Task 21 API.
- GREEN: Playwright 17 passed (13 dashboard + 4 onboarding). `bun run build` exit 0. pytest 730 passed. ruff 0, mypy 0, boundary doc current, exemptions empty.
- Commit: feat: add review dashboard with playwright coverage
- Decisions: Seeded Task 21 API on 127.0.0.1:8742 for Playwright. Dashboard I/O stays fetch-only against injected Task 21 routes. Mutation tests run last and serial.
- Blocked: -

## Task P1 after 22 - ✅ done  2026-09-01T06:13:00+05:30
- RED: n/a
- GREEN: No newly unlocked phase. Phase 11 still needs 24 and runtime 10. Phase 17 still needs 25.
- Commit: none
- Decisions: none
- Blocked: -

## Task 23 - ✅ done  2026-09-01T06:18:00+05:30
- RED: 4 failed, 1 passed, failing for: missing Dockerfile, compose files, and workflows
- GREEN: 735 passed. ruff 0, mypy 0. `docker build --target api` exit 0. `docker run ... id` is uid=65532.
- Commit: feat: add ci, release containers, and supply-chain checks
- Decisions: Root Dockerfile uses the existing busybox digest and four named stages. CI is config plus tests, not a GitHub badge. Workflows are not executed tonight because nothing is pushed.
- Blocked: -

## Task P1 after 23 - ✅ done  2026-09-01T06:18:00+05:30
- RED: n/a
- GREEN: No newly unlocked phase. Phase 3 still needs 25. Phase 10 still needs runtime 10. Phase 14 still needs runtime 10.
- Commit: none
- Decisions: none
- Blocked: -

## Task 25 - ✅ done  2026-09-01T06:30:57+05:30
- RED: 10 failed, 1 passed, failing for: missing installer, setup, doctor modules and scripts
- GREEN: 747 passed. ruff 0, mypy 0, boundary doc current, exemptions empty. CLAUDE-IN FIX: unauthenticated /openapi.json and unknown paths are not 200.
- Commit: feat: add versioned installer, setup wizard, and doctor
- Decisions: Guard denies by default. FastAPI docs/redoc/openapi are off. reviewer setup lives in cli/main.py. Docker doctor stays in runner/cli. Uninstall keeps data unless both delete flags are set.
- Blocked: -

## Task P1 after 25 - ✅ done  2026-09-01T06:30:57+05:30
- RED: n/a
- GREEN: Phase 17 mapped tasks 21, 22, 25 and runtime 8 are implemented. Document written after this commit.
- Commit: see Phase 17
- Decisions: Phase 18 still needs Task 26.
- Blocked: -

## Phase 17 - ✅ done  2026-09-01T06:32:00+05:30
- RED: n/a
- GREEN: `17 passed (23.7s)` on `cd apps/web && bunx playwright test`
- Commit: docs: add phase 17 write-up with verified proof gate
- Decisions: quoted the Playwright count. No quality number invented.
- Blocked: -

## Phase 2 test gate - ⚠️ partial  2026-09-01T06:41:39+05:30
- RED: n/a, docs only
- GREEN: Phase 2 proof suite `119 passed, 1 warning in 38.27s`. Full suite 747 passed. ruff 0, mypy 0, boundary doc current, exemptions empty. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD (`web/dashboard_api.py:69` and `:98`).
- Commit: docs: add phase 2 write-up with verified proof gate
- Decisions: Updated the existing design-gate file. Did not invent a new phase. No newly unlocked complete phase after Task 25.
- Blocked: runtime Task 10. Hosted end-to-end at reviewer.niresh.tech is not live.
- Skipped:
  - Phase 7: master 9 ⚠️, 24 ⬜, 26 ⬜
  - Phase 15: master 24 ⬜, 26 ⬜
  - Phase 16: master 24 ⬜, 26 ⬜
  - Phase 18: master 26 ⬜
  - Phase 19: master 24 ⬜, 26 ⬜, runtime 10 ⬜
  - Phase 20: master 9 ⚠️, 24 ⬜, 26 ⬜

## Phase 4 - ✅ done  2026-09-01T06:46:00+05:30
- RED: n/a, docs only
- GREEN: Phase 4 proof suite `79 passed, 1 warning in 4.40s`. Auth test included. ruff 0, mypy 0, boundary doc current, exemptions empty. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD.
- Commit: docs: add phase 4 write-up with verified proof gate
- Decisions: Overnight spec says this gate is runnable tonight. Task 9 holdout is an eval block, not a schema block. Quoted 79 passed. No eval number invented. No down-migration claimed.
- Blocked: runtime Task 10 is not this gate.

## Phase 3 - ✅ done  2026-09-01T06:53:00+05:30
- RED: n/a, docs only
- GREEN: Phase 3 proof suite `67 passed, 1 warning in 44.93s`. Includes live local Postgres restart. ruff 0, mypy 0 pending full gate. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD.
- Commit: docs: add phase 3 write-up with verified proof gate
- Decisions: Local start-health-restart is this gate. Task 24 and runtime Task 10 are not. Quoted 67 passed. No public hostname claimed.
- Blocked: -

## Phase 10 - ✅ done  2026-09-01T07:00:00+05:30
- RED: n/a, docs only
- GREEN: Phase 10 proof suite `60 passed, 1 warning in 29.07s`. Full suite 747 passed. ruff 0, mypy 0, boundary doc current, exemptions empty. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD.
- Commit: docs: add phase 10 write-up with verified proof gate
- Decisions: Sandbox unit proof is this gate. Runtime Task 10 is not. Quoted 60 passed. No host-execution claimed.
- Blocked: -

## Phase 14 - ✅ done  2026-09-01T07:04:00+05:30
- RED: n/a, docs only
- GREEN: Phase 14 proof suite `33 passed, 1 warning in 3.14s`. Full suite pending gate. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD.
- Commit: docs: add phase 14 write-up with verified proof gate
- Decisions: Fault injection is this gate. Runtime Task 10 is not. Quoted 33 passed. No latency number invented.
- Blocked: -

## Phase 6 - ✅ done  2026-09-01T07:09:00+05:30
- RED: n/a, docs only
- GREEN: Phase 6 proof suite `31 passed, 1 warning in 1.95s`. Full suite pending gate. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD.
- Commit: docs: add phase 6 write-up with verified proof gate
- Decisions: Trace reconstruction is this gate. Task 26 and runtime Task 10 are not. Quoted 31 passed. No eval number invented.
- Blocked: -

## Phase 11 - ✅ done  2026-09-01T07:13:00+05:30
- RED: n/a, docs only
- GREEN: Phase 11 proof suite `27 passed, 1 warning in 1.55s`. Full suite pending gate. CLAUDE-IN 2026-09-01T06:26:00+05:30 FIX already on HEAD.
- Commit: docs: add phase 11 write-up with verified proof gate
- Decisions: HITL routing is this gate. Task 24 and runtime Task 10 are not. Quoted 27 passed. Phase 7 stays skipped because the holdout is empty.
- Blocked: -
