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
- ✅ Runtime plan complete except Task 10: Tasks 1, 1A, 1B, 2, 2A, 2B, 3, 4, 5, 5A, 6, 7, 8, 9 all
  shipped. Work is on `main`; the `PR-REVIEWER-*` branches were consolidated and deleted.
- ✅ Master plan Tasks 1 to 6 shipped. 20 of 44 tasks done overall.
- ⬜ Runtime Task 10 (end-to-end proof) is blocked: nothing is deployed at
  `https://reviewer.niresh.tech`. The subdomain does not exist yet and has to be created:
  DNS record, TLS certificate, and a reverse proxy to the control plane. Corrected 2026-09-01;
  it is a dedicated subdomain, never the apex `niresh.tech`.
  The domain is fixed by the GitHub App registration; the host is still undecided.
- ⬜ Next work is master Task 7, then straight to Task 9. Task 9 (evals) must land before Task 11
  (the first reviewer), so there is a number to beat before there is anything to measure.
- ⬜ Phase 2 test gate, and the phases behind the remaining 23 master tasks.

## Live environment facts - ✅

- GitHub App registered 2026-08-30. App ID `4771544`. Domain `https://reviewer.niresh.tech`.
  ⚠️ The App was registered against the apex `niresh.tech`, so its **homepage URL, callback URL
  and webhook URL all still point at the wrong host** and must be updated in GitHub App settings
  before any live delivery works.
- The App private key lives at `/srv/claude/secrets/`, mode 0600, **outside the repo**. `.env` holds
  the PEM content and is mode 0600. `*.pem`, `*.key` and `secrets/` are gitignored.
- `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET` are still blank in `.env`.
- Cursor cannot commit: PID 678903, a Zed-hosted `cursor-agent` running since 20 July, injects a
  `Co-authored-by: Cursor` trailer that both commit guards correctly reject. It loaded its config
  five weeks before `attributeCommitsToAgent: false` was written. Fix is `kill 678903`. Until then
  Claude lands the commits, which works.

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
