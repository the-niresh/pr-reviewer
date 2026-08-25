import { claimReviewJob, type ReviewJob } from "@pr-reviewer/core/src/jobs/claimReviewJob";
import { completeReviewJob } from "@pr-reviewer/core/src/jobs/completeReviewJob";
import {
  db,
  runWorkerDatabaseOperation,
  type WorkerDatabaseClient,
  WorkerDatabaseOperationAbortedError,
  WorkerDatabaseOperationTimedOutError,
} from "@pr-reviewer/core/src/db/client";
import { failReviewJob } from "@pr-reviewer/core/src/jobs/failReviewJob";
import { renewReviewJobLease } from "@pr-reviewer/core/src/jobs/renewReviewJobLease";

const DEFAULT_POLL_INTERVAL_MS = 1_000;
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 30_000;
const DEFAULT_DATABASE_CALL_TIMEOUT_MS = 10_000;
const DEFAULT_LEASE_RENEWAL_INTERVAL_MS = 60_000;

export type RunReviewJob = (job: ReviewJob, signal: AbortSignal) => Promise<void>;

export async function runReviewJob(_job: ReviewJob, _signal: AbortSignal): Promise<void> {
  // Task 4 only claims and tracks work. PR review logic is added later.
}

export type WorkerOptions = {
  databaseCallTimeoutMs?: number;
  jobStore?: JobStore;
  leaseRenewalIntervalMs?: number;
  pollIntervalMs?: number;
  reportError?: (message: string) => void;
  shutdownTimeoutMs?: number;
  runJob?: RunReviewJob;
  signal?: AbortSignal;
  workerId?: string;
};

export type JobStore = {
  claim: (workerId: string, client: WorkerDatabaseClient) => Promise<ReviewJob | null>;
  complete: (jobId: string, workerId: string, client: WorkerDatabaseClient) => Promise<void>;
  fail: (jobId: string, workerId: string, error: string, client: WorkerDatabaseClient) => Promise<void>;
  renew: (jobId: string, workerId: string, client: WorkerDatabaseClient) => Promise<void>;
};

const defaultJobStore: JobStore = {
  claim: claimReviewJob,
  complete: completeReviewJob,
  fail: failReviewJob,
  renew: renewReviewJobLease,
};

export async function runWorker({
  databaseCallTimeoutMs = DEFAULT_DATABASE_CALL_TIMEOUT_MS,
  leaseRenewalIntervalMs = DEFAULT_LEASE_RENEWAL_INTERVAL_MS,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
  reportError = writeWorkerError,
  shutdownTimeoutMs = DEFAULT_SHUTDOWN_TIMEOUT_MS,
  runJob = runReviewJob,
  signal,
  workerId = `worker_${process.pid}`,
  jobStore = defaultJobStore,
}: WorkerOptions = {}): Promise<void> {
  const stopController = new AbortController();
  const stop = () => stopController.abort();

  process.once("SIGTERM", stop);
  signal?.addEventListener("abort", stop, { once: true });

  try {
    while (!stopController.signal.aborted) {
      const claimResult = await runDatabaseCall(
        "claim review job",
        (client) => jobStore.claim(workerId, client),
        stopController.signal,
        databaseCallTimeoutMs,
        reportError,
      );

      if (claimResult.kind !== "completed") {
        break;
      }

      const job = claimResult.value;

      if (stopController.signal.aborted) {
        if (job !== null) {
          await runDatabaseCall(
            "release claimed job during shutdown",
            (client) => jobStore.fail(job.id, workerId, "Worker shutdown requested before review started", client),
            stopController.signal,
            databaseCallTimeoutMs,
            reportError,
          );
        }
        break;
      }

      if (job === null) {
        await waitForNextPoll(pollIntervalMs, stopController.signal);
        continue;
      }

      const jobController = new AbortController();
      const stopJob = () => jobController.abort();
      stopController.signal.addEventListener("abort", stopJob, { once: true });
      const renewal = startLeaseRenewal({
        databaseCallTimeoutMs,
        intervalMs: leaseRenewalIntervalMs,
        job,
        jobStore,
        reportError,
        signal: jobController.signal,
        stopJob,
        workerId,
      });
      const result = await runJobUntilShutdown(runJob, job, jobController.signal, shutdownTimeoutMs);
      renewal.stop();
      stopController.signal.removeEventListener("abort", stopJob);

      if (result.kind === "completed") {
        if (result.error !== null) {
          const failResult = await runDatabaseCall(
            "fail review job",
            (client) => jobStore.fail(job.id, workerId, getErrorMessage(result.error), client),
            stopController.signal,
            databaseCallTimeoutMs,
            reportError,
          );
          if (failResult.kind !== "completed") {
            break;
          }
          continue;
        }

        const completeResult = await runDatabaseCall(
          "complete review job",
          (client) => jobStore.complete(job.id, workerId, client),
          stopController.signal,
          databaseCallTimeoutMs,
          reportError,
        );
        if (completeResult.kind !== "completed") {
          break;
        }
        continue;
      }

      if (result.kind === "stopped") {
        const failResult = await runDatabaseCall(
          "fail review job during shutdown",
          (client) => jobStore.fail(job.id, workerId, "Worker shutdown requested during review", client),
          stopController.signal,
          databaseCallTimeoutMs,
          reportError,
        );
        if (failResult.kind !== "completed") {
          break;
        }
      } else {
        reportError(`Review job ${job.id} exceeded the shutdown deadline; its lease remains for recovery`);
      }

      break;
    }
  } finally {
    process.removeListener("SIGTERM", stop);
    signal?.removeEventListener("abort", stop);
  }
}

type DatabaseCallResult<T> =
  | { kind: "completed"; value: T }
  | { kind: "aborted" }
  | { kind: "timed_out" };

async function runDatabaseCall<T>(
  name: string,
  operation: (client: WorkerDatabaseClient) => Promise<T>,
  signal: AbortSignal,
  timeoutMs: number,
  reportError: (message: string) => void,
): Promise<DatabaseCallResult<T>> {
  try {
    return { kind: "completed", value: await runWorkerDatabaseOperation(operation, { signal, timeoutMs }) };
  } catch (error) {
    if (error instanceof WorkerDatabaseOperationAbortedError) {
      reportError(`Database call aborted during shutdown: ${name}`);
      return { kind: "aborted" };
    }
    if (error instanceof WorkerDatabaseOperationTimedOutError) {
      reportError(`Database call timed out: ${name}`);
      return { kind: "timed_out" };
    }
    throw error;
  }
}

function startLeaseRenewal({
  databaseCallTimeoutMs,
  intervalMs,
  job,
  jobStore,
  reportError,
  signal,
  stopJob,
  workerId,
}: {
  databaseCallTimeoutMs: number;
  intervalMs: number;
  job: ReviewJob;
  jobStore: JobStore;
  reportError: (message: string) => void;
  signal: AbortSignal;
  stopJob: () => void;
  workerId: string;
}): { stop: () => void } {
  let active = true;
  let renewalInFlight = false;
  const timer = setInterval(() => {
    if (!active || signal.aborted || renewalInFlight) {
      return;
    }

    renewalInFlight = true;
    void runDatabaseCall(
      "renew review job lease",
      (client) => jobStore.renew(job.id, workerId, client),
      signal,
      databaseCallTimeoutMs,
      reportError,
    )
      .then((result) => {
        if (active && result.kind !== "completed") {
          stopJob();
        }
      })
      .catch((error: unknown) => {
        if (active) {
          reportError(`Review job ${job.id} lease renewal failed: ${getErrorMessage(error)}`);
          stopJob();
        }
      })
      .finally(() => {
        renewalInFlight = false;
      });
  }, intervalMs);

  return {
    stop: () => {
      active = false;
      clearInterval(timer);
    },
  };
}

type JobRunResult =
  | { kind: "completed"; error: unknown | null }
  | { kind: "stopped" }
  | { kind: "timed_out" };

async function runJobUntilShutdown(
  runJob: RunReviewJob,
  job: ReviewJob,
  signal: AbortSignal,
  shutdownTimeoutMs: number,
): Promise<JobRunResult> {
  const completion = Promise.resolve()
    .then(() => runJob(job, signal))
    .then(
      () => ({ kind: "completed" as const, error: null }),
      (error: unknown) => ({ kind: "completed" as const, error }),
    );
  const abortWaiter = createAbortWaiter(signal);
  const first = await Promise.race([completion, abortWaiter.promise]);
  abortWaiter.cancel();

  if (first.kind === "completed") {
    return first;
  }

  const bounded = await Promise.race([completion, waitForShutdownDeadline(shutdownTimeoutMs)]);
  return bounded.kind === "completed" ? { kind: "stopped" } : { kind: "timed_out" };
}

function waitForNextPoll(intervalMs: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const timer = setTimeout(onTimer, intervalMs);

    function onTimer(): void {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }

    function onAbort(): void {
      clearTimeout(timer);
      resolve();
    }

    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function createAbortWaiter(signal: AbortSignal): {
  promise: Promise<{ kind: "aborted" }>;
  cancel: () => void;
} {
  if (signal.aborted) {
    return {
      promise: Promise.resolve({ kind: "aborted" }),
      cancel: () => {},
    };
  }

  let onAbort: (() => void) | undefined;
  const promise = new Promise<{ kind: "aborted" }>((resolve) => {
    onAbort = () => resolve({ kind: "aborted" });
    signal.addEventListener("abort", onAbort, { once: true });
  });

  return {
    promise,
    cancel: () => {
      if (onAbort !== undefined) {
        signal.removeEventListener("abort", onAbort);
      }
    },
  };
}

function waitForShutdownDeadline(timeoutMs: number): Promise<{ kind: "timed_out" }> {
  return new Promise((resolve) => {
    setTimeout(() => resolve({ kind: "timed_out" }), timeoutMs);
  });
}

function writeWorkerError(message: string): void {
  process.stderr.write(`${message}\n`);
}

if (import.meta.main) {
  runWorker()
    .catch((error: unknown) => {
      process.stderr.write(`${getErrorMessage(error)}\n`);
      process.exitCode = 1;
    })
    .finally(() => db.end());
}
