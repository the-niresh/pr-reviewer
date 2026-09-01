# Postgres queue benchmark (Task 18)

Expected worker count: 4

This is the ADR-002 measurement. Claim p99 at 4 workers was recorded by
`scripts/queue_benchmark.py` against local Postgres. Redis is not in this
stack. Reversal trigger remains claim latency above 2 seconds.

Exact command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run python scripts/queue_benchmark.py
worker_count=4
jobs=40
pending_depth_after_enqueue=40
claimed=40
p99_claim_ms=11.710
```

p99 claim latency: 11.710 ms (4 workers, 40 jobs).
Pending depth after enqueue, empty table: 40.

Not adding Redis.
