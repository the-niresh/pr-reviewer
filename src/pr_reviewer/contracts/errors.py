"""Closed-set error classification for hosted job failure records (Runtime Task 1B).

review_jobs.last_error is a hosted column. control_plane/boundary.py's ALLOWLIST entry for it
already promised the value stays "a message or exception class name, never a diff, stack trace,
or file content" -- but before this module, fail_review_job(job_id, worker_id, error: str) took
any string at all, so that promise was documented and enforced by nobody. ReviewJobErrorClass
makes prose impossible to write there, not merely discouraged: there is no constructor path from
an arbitrary string to a ReviewJobErrorClass, so a caller cannot put a stack trace, a file path,
or a diff fragment into Neon even by accident.

Two members exist because two things make a review job fail today, both in worker/main.py's
run_worker: an exception raised while running the review (worker_crashed), and the worker being
asked to shut down while a review was still in flight (shutdown_requested). Which exception, if
any, is local detail that stays in the runner's own logs; the hosted column only needs to record
which of these two things happened.
"""

from __future__ import annotations

from enum import StrEnum


class ReviewJobErrorClass(StrEnum):
    WORKER_CRASHED = "worker_crashed"
    SHUTDOWN_REQUESTED = "shutdown_requested"
