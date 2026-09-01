# Blocked: human actions only

Each item is a human action. Order is dependency order. Each line is the one
thing that unblocks it.

## 1. Fill the candidate sheet

Sheet: `datasets/private/candidate_sheet.jsonl`.
FoodSpector `write-sheet --max-cases 40` on 2026-09-01 printed
`candidates=37 skipped=3`. Every `verdict` is still empty.

**You need to:** set `verdict` to `include` or `exclude` on every row. Include
rows also need `human_auditor`, `split`, and `labels`. Then run
`uv run python -m pr_reviewer.evals.holdout_sheet build-holdout`.

Unblocks: Task 9 frozen holdout, eval reports, Task 26 quality numbers.

## 2. Create the DNS A record

**You need to:** add `reviewer.niresh.tech` A `76.13.243.12`.

Unblocks: Let's Encrypt for that host.

## 3. Apply the Traefik overlay

Config is on disk (`docker-compose.hosted.yml`, `deploy/traefik/reviewer.yml`,
`docs/RUNBOOK.md`). Nothing is applied.

**You need to:** merge the hosted overlay onto the running control plane so
Traefik v2.11 serves `Host(reviewer.niresh.tech)`.

Unblocks: public HTTPS on that host.

## 4. Move GitHub App 4771544 off the apex

**You need to:** set homepage, callback, and webhook to:

- `https://reviewer.niresh.tech`
- `https://reviewer.niresh.tech/api/auth/github/callback`
- `https://reviewer.niresh.tech/api/github/webhook`

Unblocks: live GitHub deliveries. Needs 2 and 3 first.

## 5. Publish a GitHub Release

Local install of `pr-reviewer-0.1.0-compose.release.yml` is proved.
A GitHub-hosted asset is not.

**You need to:** push and create the release. Do not ask an agent to push.

Unblocks: Task 25 GitHub-hosted install.

## 6. Run the FoodSpector shadow (Task 24)

**You need to:** after 2-4, pair the FoodSpector runner with auto-post
disabled and collect at least 30 non-draft PRs over at least 14 days.

Unblocks: Task 24, runtime Task 10, Task 26 shadow totals.

## 7. Publish measured quality (Task 26)

**You need to:** after 1 and 6, write precision, recall, cost per PR, and
shadow totals from those runs. Do not invent them.

Unblocks: Task 26 measured-proof steps.

## Accepted risk

A historical `git add -A` put a live hosted database URL on GitHub. It is not
in the current tree. This is an accepted risk, not an open action.
