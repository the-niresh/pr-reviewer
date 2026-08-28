# Session handoff - 2026-08-28

| Mark | Means |
|---|---|
| ⬜ | Not done yet | 
| ✅ | Done or agreed |
| ❌ | Deliberately not doing |
| ❓ | Open, waiting on the owner |
| ⚠️ | Trap, read first |

**Purpose - ✅:** What a fresh session needs to not re-derive today's decisions badly. Read this,
then the phase records, then the plans.

## Where things stand - ✅

- ✅ Phase 0 approved. Record: `docs/phases/phase-0-cognitive-design.md`.
- ✅ Phase 1 approved. Record: `docs/phases/phase-1-system-architecture.md`.
- ✅ Phase 2 **design gate** approved. Test gate stays open until the end of the build.
- ✅ Runtime Task 1 and Task 1A shipped on `PR-REVIEWER-3`, not pushed.
- ⬜ Runtime Task 2 (pairing) is next. Prompt was given, work not started.
- ⬜ Phase 2 test gate, Phases 3 onward.

## Decisions made today that are not obvious from the code - ✅

- ✅ **Repo transfer:** data stays with the OLD installation. A repo moving orgs keeps its numeric
  ID, so following it would leak across tenants. Cost accepted: you lose history moving your own repo.
- ✅ **Second machine pairing an assigned repo:** refuse, do not auto-revoke. Silent takeover is a
  bad property even though the attacker needs the GitHub account anyway.
- ✅ **Authorization returns a typed union**, not a raise. `RepositoryAuthorization | AuthorizationDenied`
  forces narrowing under mypy strict, so forgetting to check is a type error.
- ✅ **`assert_no_private_columns` allowlists by column TYPE.** text/varchar/char/jsonb/bytea/arrays
  need an entry with a reason; scalars auto-permit. An integer cannot hold a diff.
- ✅ **No agentic exploration loop in v1.** Recorded with a revisit trigger in the master plan.
- ✅ **Migrations use UTC timestamp prefixes.** Only 0001-0004 keep numbers.

## Rules learned the hard way today - ⚠️

- ⚠️ **A denial reason is part of the tenancy boundary.** It must be computable from data the caller
  may already see. Task 1 shipped a leak: distinguishing "not yours" from "does not exist" required
  an unscoped query. Two indistinguishable states get one reason.
- ⚠️ **Three carriers of knowledge, ranked.** Executable (tests, constraints, types) beats derived
  (code graph, git history) beats written (instruction files). Most people reach for written because
  it is quick. It is the weakest. FoodSpector's own repo proves it: rule 1 is enforced by 14 test
  files, rule 5 is a sentence, and only rule 5 is at risk from an agent.
- ⚠️ **A test that passes on day one may be vacuous.** `test_package_boundaries.py` solves this with
  a hardcoded `EXPECTED_EXISTING_PACKAGES` snapshot that fails when reality drifts. Reuse that shape.
- ⚠️ **Verify the declared file list, not just behaviour.** Task 1 was reported and verified complete
  with `docs/DATA_BOUNDARIES.md` never written. `scripts/check_task_files.py` now catches that.
- ⚠️ **`.env` points DATABASE_URL at Neon** and `config.py` calls `load_dotenv()`, so
  `pr-reviewer-db-migrate` writes to the hosted dev database while tests use local Docker on 54329.
  The two drift silently.

## How to work with Cursor here - ✅

The owner is learning, not outsourcing. Every task prompt uses the same six-step loop: summary and
hardest decision first, owner answers the design decisions, failing tests only in one commit with
real failure output shown, then implementation, then Cursor quizzes the owner, and no diff is
accepted that the owner cannot explain. Do not shortcut it, and do not answer the design decisions
on the owner's behalf. Give them the tradeoffs and a recommendation.

## Open decisions - ❓

- ❓ Should `docs/phases/` be tracked by git? It is currently untracked.
- ❓ Should the four ADRs move to a browsable `docs/adr/` directory?
- ❓ Context budget per model for Task 10A, which needs the Phase 8 model choice first.
- ❓ Which host and domain runs the control plane, and monthly cost.
