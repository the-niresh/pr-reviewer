# Phase 19 - ⚠️ CI/CD for AI and FoodSpector Release

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ LOCAL RELEASE-CONFIG AND EVAL GATES REPRODUCED, HOSTED ACTIONS AND
FOODSPECTOR SHADOW NOT RUN 2026-09-01.** Master Tasks 20 and 23 are treated as
done at HEAD. Product-runtime Task 9 is ✅. Master Tasks 24 and 26 stay ⬜.
Product-runtime Task 10 stays ⬜. Those three are not this local config gate.

## 1 - ✅ Python and frontend CI is written as workflow config

`.github/workflows/ci.yml` runs on pull_request and on push to `main`
(`.github/workflows/ci.yml:3`). The job uses a digest-pinned pgvector image
(`.github/workflows/ci.yml:13`). Named steps are lock (`uv lock --check`),
ruff, mypy, pytest, `migration-from-empty`, `migration-upgrade`, bun tests,
frontend build, Playwright, a secret scan, and the hosted boundary doc check
(`.github/workflows/ci.yml:18`).
`test_ci_workflow_runs_the_required_gates` (`tests/test_release_config.py:108`)
asserts those needles stay in the file.

⚠️ This checkout has not been pushed. GitHub Actions has not executed these
steps. The deliverable tonight is the workflow file plus the config tests, not
a green Actions badge.

## 2 - ✅ Release images are non-root, digest-pinned, and free of secret build args

The root `Dockerfile` has four named stages. Each sets `USER 65532:65532`
(`Dockerfile:2`, `Dockerfile:7`, `Dockerfile:12`, `Dockerfile:17`). Every
`FROM` is `busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662`.
`test_root_dockerfile_is_non_root_and_digest_pinned`
(`tests/test_release_config.py:86`) rejects root, `:latest`, and secret-named
`ARG`s.

`compose.release.yml` sets `user: "65532:65532"` and a `healthcheck` on each
service (`compose.release.yml:7`). `docker-compose.ci.yml` pins pgvector by
digest and runs it as `70:70` (`docker-compose.ci.yml:3`).
`test_compose_release_and_ci_are_non_root_healthy_and_pinned`
(`tests/test_release_config.py:99`) covers both files.

## 3 - ✅ Applied migration names cannot be silently renamed

`test_migration_filenames_are_unique_prefixed_and_not_renamed`
(`tests/test_release_config.py:130`) checks hosted, local SQLite, and local
Postgres directories. Names must match `0000_`, `000N_`, or a 12-digit prefix.
`REQUIRED_APPLIED_MIGRATIONS` (`tests/test_release_config.py:28`) is the set
that must still exist. A rename of an already-applied file fails the test.

## 4 - ✅ Eval regression gates exist and refuse an empty holdout

`compare_eval_reports` (`evals/regression_gate.py:48`) blocks on precision,
false findings per PR, high-value recall, cost, and latency against both the
baseline report and `EvalThresholds`. The tests use synthetic `EvalRun`
objects (`tests/test_eval_regression_gate.py:60`).
`test_public_holdout_baseline_is_still_blocked`
(`tests/test_eval_regression_gate.py:110`) is the real-dataset refusal.

`consider_feedback` (`evals/feedback_candidates.py:43`) never rewrites prompts,
policy, labels, or routing (`evals/feedback_candidates.py:72`). One dispute is
not a candidate (`tests/test_feedback_candidates.py:17`).

Brier score and calibration buckets are reported
(`evals/regression_gate.py:78`). Routing does not read confidence
(`tests/test_eval_regression_gate.py:133`).

## 5 - ✅ Local install still verifies a checksummed archive

`scripts/install.sh` copies the archive, runs `sha256sum -c`, then copies into
`--prefix` (`scripts/install.sh:39`). A bad digest is rejected
(`tests/test_installer.py:60`). `test_install_runs_in_clean_linux_container`
runs that script as uid 65532 in pinned busybox.

⚠️ That is a local checksummed file, not a public GitHub Releases URL. Task 26
is not this gate.

## 6 - ⚠️ Release workflow writes checksums and an SBOM, not a signed canary

`.github/workflows/release.yml` is `workflow_dispatch` only
(`.github/workflows/release.yml:4`). It writes `dist/SHA256SUMS` and a syft
SPDX SBOM (`.github/workflows/release.yml:13`).
`test_release_workflow_writes_checksums_and_sbom`
(`tests/test_release_config.py:123`) accepts `cosign` or `syft` or `anchore`.
This file uses syft. It does not invoke cosign.

The container-scan step is:

```text
echo "scan pinned release images"
```

(`.github/workflows/release.yml:20`). That is a placeholder, not a scanner.
There is no canary job and no rollback job in `.github/workflows/`.

## 7 - ⚠️ FoodSpector shadow is not this gate

The phase proof gate also requires FoodSpector to complete at least 30
non-draft PRs over at least 14 days with measured release gates recorded.
Task 24 is ⬜. `datasets/public/eval_cases.jsonl` has one row: `public-1`,
`split=dev`. `run_diff_only_baseline` raises `BaselineBlocked`. This document
invents no PR count, no shadow duration, and no release-gate metric from a
live repo.

## Design gate - ⚠️ config closed, hosted and shadow open

✅ Release-config tests pin non-root digest images, unique migrations, CI
needles, checksums, and an SBOM tool. Eval gates block synthetic regressions
and refuse an empty holdout. Local install verifies sha256.

⚠️ GitHub Actions has not run. The container scan is an echo. There is no
signed canary or workflow rollback. FoodSpector shadow is not started.
Runtime Task 10 is not this gate.

## Test gate - ⚠️ partial

The proof gate is: release checks pass, install proof passes from a versioned
asset, and FoodSpector completes at least 30 non-draft PRs over at least 14
days with the measured release gates recorded.

Release-config and local-install half, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_release_config.py tests/test_eval_regression_gate.py tests/test_feedback_candidates.py tests/test_installer.py::test_install_script_verifies_checksum_and_rejects_bad_digest tests/test_installer.py::test_install_runs_in_clean_linux_container
.........................                                                [100%]
25 passed, 1 warning in 1.84s
```

`test_ci_workflow_runs_the_required_gates` and
`test_root_dockerfile_is_non_root_and_digest_pinned` are the release-check
proof. `test_install_script_verifies_checksum_and_rejects_bad_digest` and
`test_install_runs_in_clean_linux_container` are the local versioned-asset
install. `test_unauthenticated_docs_and_unknown_paths_are_not_ok` is the
06:11 FIX.

FoodSpector and holdout half, same checkout:

```text
$ uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline; cases = load_public_eval_cases(); print([(c.id, c.split) for c in cases]); run_diff_only_baseline(cases, FixtureReviewer.perfect())"
[('public-1', 'dev')]
BaselineBlocked: holdout is empty; refusing to report a baseline
```

No 14-day FoodSpector count is reported here because none was produced.
`FixtureReviewer` was the reviewer. No model HTTP client ran.

⚠️ Task 24 (FoodSpector shadow), Task 26 (hiring README), and runtime Task 10
(hosted end-to-end at reviewer.niresh.tech) are not this gate.

## Settled - ✅

- ✅ CI workflow files name ruff, mypy, pytest, migrations, bun, Playwright,
  and the boundary-doc check.
- ✅ Release images drop to uid 65532 and pin by digest.
- ✅ Applied migration filenames cannot be renamed without failing a test.
- ✅ Eval regression gates block synthetic regressions. An empty holdout
  refuses a baseline.
- ✅ One dispute does not rewrite prompts, policy, labels, or routing.
- ✅ Local install verifies sha256 before copying.

## Open Decisions - ❓

- ❓ When a public GitHub Release URL exists, whether the morning install
  proof uses that URL or keeps the local checksummed archive.
- ❓ Which scanner replaces `echo "scan pinned release images"` before the
  first real release.
- ❓ Who runs the 14-day FoodSpector shadow after reviewer.niresh.tech is
  live.
