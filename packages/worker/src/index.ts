import { claimReviewJob, type ReviewJob } from "@pr-reviewer/core/src/jobs/claimReviewJob";
import { completeReviewJob } from "@pr-reviewer/core/src/jobs/completeReviewJob";
import { db } from "@pr-reviewer/core/src/db/client";
import { failReviewJob } from "@pr-reviewer/core/src/jobs/failReviewJob";

const DEFAULT_POLL_INTERVAL_MS = 1_000;

export type RunReviewJob = (job: ReviewJob) => Promise<void>;

export async function runReviewJob(_job: ReviewJob): Promise<void> {
  // Task 4 only claims and tracks work. PR review logic is added later.
}

export type WorkerOptions = {
  pollIntervalMs?: number;
  runJob?: RunReviewJob;
  workerId?: string;
};

export async function runWorker({
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
  runJob = runReviewJob,
  workerId = `worker_${process.pid}`,
}: WorkerOptions = {}): Promise<void> {
  const stopController = new AbortController();
  const stop = () => stopController.abort();

  process.once("SIGTERM", stop);

  try {
    while (!stopController.signal.aborted) {
      const job = await claimReviewJob(workerId);

      if (job === null) {
        await waitForNextPoll(pollIntervalMs, stopController.signal);
        continue;
      }

      try {
        await runJob(job);
      } catch (error) {
        await failReviewJob(job.id, getErrorMessage(error));
        continue;
      }

      await completeReviewJob(job.id);
    }
  } finally {
    process.removeListener("SIGTERM", stop);
  }
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

if (import.meta.main) {
  runWorker()
    .catch((error: unknown) => {
      process.stderr.write(`${getErrorMessage(error)}\n`);
      process.exitCode = 1;
    })
    .finally(() => db.end());
}
