"""Postgres queue benchmark at the expected v1 worker count.

ADR-002's reversal trigger is claim latency above 2 seconds. This module measures
that number. It is not Redis.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pr_reviewer.jobs.claim_review_job import claim_review_job
from pr_reviewer.jobs.enqueue_review_job import enqueue_review_job

EXPECTED_WORKER_COUNT = 4
_BENCHMARK_DEADLINE_SECONDS = 30.0


@dataclass(frozen=True)
class QueueBenchmarkResult:
    worker_count: int
    jobs: int
    p99_claim_ms: float


def run_queue_benchmark(worker_count: int, jobs: int) -> QueueBenchmarkResult:
    for index in range(jobs):
        enqueue_review_job(f"benchmark-{index}", "pull_request", {})

    def worker(worker_id: str) -> list[float]:
        samples: list[float] = []
        deadline = time.monotonic() + _BENCHMARK_DEADLINE_SECONDS
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
            samples.extend(future.result(timeout=_BENCHMARK_DEADLINE_SECONDS))
    ordered = sorted(samples)
    p99 = ordered[int(0.99 * (len(ordered) - 1))] if ordered else 0.0
    return QueueBenchmarkResult(
        worker_count=worker_count, jobs=jobs, p99_claim_ms=p99
    )
