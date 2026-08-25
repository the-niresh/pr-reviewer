from __future__ import annotations

import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from pr_reviewer.db.client import close_pool
from pr_reviewer.jobs import (
    ReviewJob,
    claim_review_job,
    complete_review_job,
    fail_review_job,
    renew_review_job_lease,
)

DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 30.0
DEFAULT_LEASE_RENEWAL_INTERVAL_SECONDS = 60.0

RunReviewJob = Callable[[ReviewJob, threading.Event], None]


@dataclass(frozen=True)
class JobStore:
    claim: Callable[[str], ReviewJob | None] = claim_review_job
    complete: Callable[[str, str], None] = complete_review_job
    fail: Callable[[str, str, str], None] = fail_review_job
    renew: Callable[[str, str], None] = renew_review_job_lease


def run_review_job(job: ReviewJob, stop_event: threading.Event) -> None:
    del job, stop_event


def write_worker_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def run_worker(
    *,
    job_store: JobStore | None = None,
    lease_renewal_interval_seconds: float = DEFAULT_LEASE_RENEWAL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    report_error: Callable[[str], None] = write_worker_error,
    run_job: RunReviewJob = run_review_job,
    shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    stop_event: threading.Event | None = None,
    worker_id: str = "worker_python",
) -> None:
    store = job_store or JobStore()
    stop = stop_event or threading.Event()
    iterations = 0

    while not stop.is_set():
        if max_iterations is not None and iterations >= max_iterations:
            return
        iterations += 1

        job = store.claim(worker_id)
        if job is None:
            stop.wait(poll_interval_seconds)
            continue

        job_stop = threading.Event()
        renewal = start_lease_renewal(
            interval_seconds=lease_renewal_interval_seconds,
            job=job,
            report_error=report_error,
            stop_event=job_stop,
            store=store,
            worker_id=worker_id,
        )
        try:
            run_job_with_shutdown_deadline(
                job=job,
                run_job=run_job,
                stop_event=stop,
                job_stop_event=job_stop,
                shutdown_timeout_seconds=shutdown_timeout_seconds,
            )
        except BaseException as error:
            store.fail(job.id, worker_id, get_error_message(error))
            continue
        finally:
            renewal.stop()

        if stop.is_set():
            store.fail(job.id, worker_id, "Worker shutdown requested during review")
            return

        store.complete(job.id, worker_id)


@dataclass(frozen=True)
class LeaseRenewal:
    stop: Callable[[], None]


def start_lease_renewal(
    *,
    interval_seconds: float,
    job: ReviewJob,
    report_error: Callable[[str], None],
    stop_event: threading.Event,
    store: JobStore,
    worker_id: str,
) -> LeaseRenewal:
    def loop() -> None:
        while not stop_event.wait(interval_seconds):
            try:
                store.renew(job.id, worker_id)
            except BaseException as error:
                report_error(
                    f"Review job {job.id} lease renewal failed: {get_error_message(error)}"
                )
                stop_event.set()

    thread = threading.Thread(target=loop, name=f"lease-renewal-{job.id}", daemon=True)
    thread.start()

    def stop() -> None:
        stop_event.set()
        thread.join(timeout=1.0)

    return LeaseRenewal(stop=stop)


def run_job_with_shutdown_deadline(
    *,
    job: ReviewJob,
    run_job: RunReviewJob,
    stop_event: threading.Event,
    job_stop_event: threading.Event,
    shutdown_timeout_seconds: float,
) -> None:
    error: list[BaseException] = []

    def target() -> None:
        try:
            run_job(job, job_stop_event)
        except BaseException as caught:
            error.append(caught)

    thread = threading.Thread(target=target, name=f"review-job-{job.id}")
    thread.start()

    while thread.is_alive():
        if stop_event.wait(0.05):
            job_stop_event.set()
            thread.join(timeout=shutdown_timeout_seconds)
            if thread.is_alive():
                raise TimeoutError(
                    "Review job "
                    f"{job.id} exceeded the shutdown deadline; its lease remains for recovery"
                )
            return
        time.sleep(0.01)

    thread.join()
    if error:
        raise error[0]


def get_error_message(error: BaseException) -> str:
    return str(error) or error.__class__.__name__


def main() -> None:
    stop_event = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        run_worker(stop_event=stop_event)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
