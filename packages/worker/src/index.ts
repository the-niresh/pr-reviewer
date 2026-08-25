import { claimReviewJob, type ReviewJob } from "@pr-reviewer/core/src/jobs/claimReviewJob";
import { completeReviewJob } from "@pr-reviewer/core/src/jobs/completeReviewJob";
import { db } from "@pr-reviewer/core/src/db/client";
import { failReviewJob } from "@pr-reviewer/core/src/jobs/failReviewJob";

const DEFAULT_POLL_INTERVAL_MS = 1_000;
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 30_000;

export type RunReviewJob = (job: ReviewJob, signal: AbortSignal) => Promise<void>;

export async function runReviewJob(_job: ReviewJob, _signal: AbortSignal): Promise<void> {
  // Task 4 only claims and tracks work. PR review logic is added later.
}

export type WorkerOptions = {
  pollIntervalMs?: number;
  shutdownTimeoutMs?: number;
  runJob?: RunReviewJob;
  signal?: AbortSignal;
  workerId?: string;
};

export async function runWorker({
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
  shutdownTimeoutMs = DEFAULT_SHUTDOWN_TIMEOUT_MS,
  runJob = runReviewJob,
  signal,
  workerId = `worker_${process.pid}`,
}: WorkerOptions = {}): Promise<void> {
  const stopController = new AbortController();
  const stop = () => stopController.abort();

  process.once("SIGTERM", stop);
  signal?.addEventListener("abort", stop, { once: true });

  try {
    while (!stopController.signal.aborted) {
      const job = await claimReviewJob(workerId);

      if (stopController.signal.aborted) {
        if (job !== null) {
          await failReviewJob(job.id, workerId, "Worker shutdown requested before review started");
        }
        break;
      }

      if (job === null) {
        await waitForNextPoll(pollIntervalMs, stopController.signal);
        continue;
      }

      const result = await runJobUntilShutdown(runJob, job, stopController.signal, shutdownTimeoutMs);

      if (result.kind === "completed") {
        if (result.error !== null) {
          await failReviewJob(job.id, workerId, getErrorMessage(result.error));
          continue;
        }

        await completeReviewJob(job.id, workerId);
        continue;
      }

      if (result.kind === "stopped") {
        await failReviewJob(job.id, workerId, "Worker shutdown requested during review");
      }

      break;
    }
  } finally {
    process.removeListener("SIGTERM", stop);
    signal?.removeEventListener("abort", stop);
  }
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

if (import.meta.main) {
  runWorker()
    .catch((error: unknown) => {
      process.stderr.write(`${getErrorMessage(error)}\n`);
      process.exitCode = 1;
    })
    .finally(() => db.end());
}
