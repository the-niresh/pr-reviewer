# Blocked: human actions only

Each item needs a human. Each line is the one action that unblocks it.

## Frozen eval holdout

The public dataset has one `dev` case and zero `holdout` cases.
`run_diff_only_baseline` raises `BaselineBlocked`.

**You need to:** audit the mined FoodSpector candidates and attach a named
human auditor so holdout rows can exist.

## Control plane hostname and GitHub App URLs

Runtime Task 10 and Task 24 cannot start without a public host.

**You need to:**

1. Add a DNS A record for `reviewer.niresh.tech` pointing at `76.13.243.12`.
2. Add the Traefik v2.11 router for that host.
3. Point GitHub App `4771544` homepage, callback, and webhook URLs at
   `reviewer.niresh.tech`, not the apex.

## FoodSpector shadow (Task 24)

**You need to:** do the hostname work above, pair the FoodSpector runner with
auto-post disabled, then collect at least 30 non-draft PRs over at least 14
days.

## Task 26 measured quality

Architecture, screenshots, limits, retention, rollback, Redis rationale, and
secret scans are on disk. Precision, recall, cost per PR, and shadow totals
are not.

**You need to:** finish the holdout audit first. Do not invent those numbers.

## Accepted risk

A historical `git add -A` put a live hosted database URL on GitHub. It is not
in the current tree. This is an accepted risk, not an open action.
