# Blocked: human actions only

Written after Tasks R1 through R7 on 2026-09-01. HEAD should be the Done Means
audit commit. Nothing is pushed.

Each item is still blocked. Each line is the one action that unblocks it.

| Mark | Meaning |
|---|---|
| ❌ | blocked on a human |
| ❓ | open question |

## ❌ Frozen eval holdout

Phases 7, 8, 9, 16, and 20, plus Task 19's specialist comparison, stop here.
The harness raises `BaselineBlocked: holdout is empty; refusing to report a baseline`.

**You need to:** audit the mined FoodSpector candidates and attach a named
human auditor so holdout rows can exist. About 1 to 2 hours.

## ❌ Control plane hostname and GitHub App URLs

Runtime Task 10 and Task 24 cannot start without this.

**You need to:**

1. Add a DNS A record for `reviewer.niresh.tech` pointing at `76.13.243.12`.
2. Add the Traefik v2.11 router for that host.
3. Point GitHub App `4771544` homepage, callback, and webhook URLs at
   `reviewer.niresh.tech`, not the apex.

## ❌ FoodSpector shadow (Task 24)

**You need to:** do the hostname work above, pair the FoodSpector runner with
auto-post disabled, then collect at least 30 non-draft PRs over at least 14
days.

## ❌ Leaked Neon URL

A historical `git add -A` put a live Neon URL on GitHub. It is not in the
current tree. Rotation was forbidden tonight.

**You need to:** rotate that Neon credential when you are ready. Do not paste
it into chat.

## ❓ After the holdout exists

Task 26's remaining measured README numbers (precision, recall, cost per PR)
and enabling retrieval or specialists. Not tonight.

## Not blocked on you for local proof

Queue p99 at 4 workers is recorded in `docs/QUEUE_BENCHMARK.md`. Architecture,
security, demo screenshots, and the hiring README landed in R3 through R6.
`HOSTED_EXEMPTIONS` is still empty.
