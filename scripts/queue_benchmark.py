"""Record Postgres queue claim latency and pending depth at the v1 worker count.

Run with:
  flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run python scripts/queue_benchmark.py

This truncates local review_jobs and github_deliveries first so depth is the
jobs this run enqueued, not leftovers from pytest.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

from pr_reviewer.config import default_database_url

os.environ.setdefault("DATABASE_URL", default_database_url())

from pr_reviewer.control_plane.ops import queue_metrics  # noqa: E402
from pr_reviewer.db.client import close_pool, connection  # noqa: E402
from pr_reviewer.db.migrate import migrate  # noqa: E402
from pr_reviewer.jobs.claim_review_job import claim_review_job  # noqa: E402
from pr_reviewer.jobs.enqueue_review_job import enqueue_review_job  # noqa: E402
from pr_reviewer.reliability.queue_benchmark import (  # noqa: E402
    EXPECTED_WORKER_COUNT,
    QueueBenchmarkResult,
)

DEADLINE_SECONDS = 30.0

JOBS = 40


def _drain(worker_count: int) -> list[float]:
    def worker(worker_id: str) -> list[float]:
        samples: list[float] = []
        deadline = time.monotonic() + DEADLINE_SECONDS
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"queue benchmark worker {worker_id} missed its deadline"
                )
            started = time.perf_counter()
            job = claim_review_job(worker_id)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if job is None:
                return samples
            samples.append(elapsed_ms)

    samples: list[float] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [
            pool.submit(worker, f"bench-worker-{index}") for index in range(worker_count)
        ]
        for future in futures:
            samples.extend(future.result(timeout=DEADLINE_SECONDS))
    return samples


def main() -> int:
    migrate()
    with connection() as conn, conn.transaction():
        conn.execute(
            "truncate github_deliveries, review_jobs restart identity cascade"
        )
    for index in range(JOBS):
        result = enqueue_review_job(f"r2-bench-{index}", "pull_request", {})
        if result != "enqueued":
            raise SystemExit(f"enqueue failed for r2-bench-{index}: {result}")
    depth = queue_metrics().depth
    samples = _drain(EXPECTED_WORKER_COUNT)
    ordered = sorted(samples)
    p99 = ordered[int(0.99 * (len(ordered) - 1))] if ordered else 0.0
    summary = QueueBenchmarkResult(
        worker_count=EXPECTED_WORKER_COUNT, jobs=JOBS, p99_claim_ms=p99
    )
    print(f"worker_count={summary.worker_count}")
    print(f"jobs={summary.jobs}")
    print(f"pending_depth_after_enqueue={depth}")
    print(f"claimed={len(samples)}")
    print(f"p99_claim_ms={summary.p99_claim_ms:.3f}")
    close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
