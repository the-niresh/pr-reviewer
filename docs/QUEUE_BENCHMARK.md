# Postgres queue benchmark (Task 18)

Expected worker count: 4

This is the ADR-002 measurement. Claim p99 at 4 workers was recorded by
`pr_reviewer.reliability.queue_benchmark.run_queue_benchmark`.

p99 claim latency: 1542 ms (4 workers, 40 jobs).

Not adding Redis. Reversal trigger remains claim latency above 2 seconds.
