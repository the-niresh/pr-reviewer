import { afterEach, describe, expect, it, vi } from "vitest";

const { claimReviewJob, completeReviewJob, failReviewJob, renewReviewJobLease } = vi.hoisted(() => ({
  claimReviewJob: vi.fn(),
  completeReviewJob: vi.fn(),
  failReviewJob: vi.fn(),
  renewReviewJobLease: vi.fn(),
}));

vi.mock("@pr-reviewer/core/src/jobs/claimReviewJob", () => ({ claimReviewJob }));
vi.mock("@pr-reviewer/core/src/jobs/completeReviewJob", () => ({ completeReviewJob }));
vi.mock("@pr-reviewer/core/src/jobs/failReviewJob", () => ({ failReviewJob }));
vi.mock("@pr-reviewer/core/src/jobs/renewReviewJobLease", () => ({ renewReviewJobLease }));
vi.mock("@pr-reviewer/core/src/db/client", () => ({ db: { end: vi.fn() } }));

import { runWorker } from "./index";

describe("runWorker", () => {
  afterEach(() => {
    claimReviewJob.mockReset();
    completeReviewJob.mockReset();
    failReviewJob.mockReset();
    renewReviewJobLease.mockReset();
  });

  it("stops an idle worker when SIGTERM fires", async () => {
    claimReviewJob.mockResolvedValue(null);
    const worker = runWorker({ pollIntervalMs: 60_000 });

    await waitFor(() => expect(claimReviewJob).toHaveBeenCalledOnce());
    process.emit("SIGTERM");

    await expect(settlesWithin(worker, 100)).resolves.toBe(true);
  });

  it("requeues cooperative active work when its external abort signal fires", async () => {
    const controller = new AbortController();
    claimReviewJob.mockResolvedValueOnce({ id: "job-1", status: "running" });
    const runJob = vi.fn(
      (_job: unknown, signal: AbortSignal) =>
        new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true })),
    );
    const worker = runWorker({
      signal: controller.signal,
      shutdownTimeoutMs: 100,
      runJob,
      reportError: vi.fn(),
    });

    await waitFor(() => expect(runJob).toHaveBeenCalledOnce());
    controller.abort();

    await expect(settlesWithin(worker, 150)).resolves.toBe(true);
    expect(completeReviewJob).not.toHaveBeenCalled();
    expect(failReviewJob).toHaveBeenCalledWith("job-1", expect.any(String), expect.any(String));
  });

  it("returns after the shutdown deadline when active work ignores abort", async () => {
    const controller = new AbortController();
    claimReviewJob.mockResolvedValueOnce({ id: "job-1", status: "running" });
    const runJob = vi.fn((_job: unknown, _signal: AbortSignal) => new Promise<void>(() => {}));
    const worker = runWorker({
      signal: controller.signal,
      shutdownTimeoutMs: 20,
      runJob,
      reportError: vi.fn(),
    });

    await waitFor(() => expect(runJob).toHaveBeenCalledOnce());
    controller.abort();

    await expect(settlesWithin(worker, 100)).resolves.toBe(true);
    expect(failReviewJob).not.toHaveBeenCalled();
  });

  it("stops after shutdown when a claim database call hangs", async () => {
    const controller = new AbortController();
    const reportError = vi.fn();
    claimReviewJob.mockImplementation(() => new Promise(() => {}));
    const worker = runWorker({
      signal: controller.signal,
      databaseCallTimeoutMs: 60_000,
      reportError,
    });

    await waitFor(() => expect(claimReviewJob).toHaveBeenCalledOnce());
    controller.abort();

    await expect(settlesWithin(worker, 100)).resolves.toBe(true);
    expect(reportError).toHaveBeenCalledWith(expect.stringContaining("claim"));
  });

  it("renews an active job lease before the lease can expire", async () => {
    const controller = new AbortController();
    claimReviewJob.mockResolvedValueOnce({ id: "job-1", status: "running" });
    renewReviewJobLease.mockResolvedValue(undefined);
    const runJob = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          setTimeout(() => {
            controller.abort();
            resolve();
          }, 30);
        }),
    );

    await runWorker({
      signal: controller.signal,
      leaseRenewalIntervalMs: 5,
      runJob,
      reportError: vi.fn(),
    });

    expect(renewReviewJobLease).toHaveBeenCalledWith("job-1", expect.any(String));
    expect(completeReviewJob).not.toHaveBeenCalled();
  });
});

async function settlesWithin(promise: Promise<void>, timeoutMs: number): Promise<boolean> {
  return Promise.race([
    promise.then(() => true),
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), timeoutMs)),
  ]);
}

async function waitFor(assertion: () => void): Promise<void> {
  const deadline = Date.now() + 100;

  while (true) {
    try {
      assertion();
      return;
    } catch (error) {
      if (Date.now() >= deadline) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  }
}
