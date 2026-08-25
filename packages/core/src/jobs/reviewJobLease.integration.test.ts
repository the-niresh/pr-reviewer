import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";
import { db } from "../db/client";
import { migrate } from "../db/migrate";
import { claimReviewJob } from "./claimReviewJob";
import { completeReviewJob } from "./completeReviewJob";
import { failReviewJob } from "./failReviewJob";
import { renewReviewJobLease } from "./renewReviewJobLease";

describe("review job leases", () => {
  let deliveryNumber = 0;
  let createdJobIds: string[] = [];

  beforeAll(async () => {
    await migrate();
  });

  beforeEach(() => {
    createdJobIds = [];
  });

  afterEach(async () => {
    if (createdJobIds.length === 0) {
      return;
    }

    await db.query(
      `update review_jobs
       set status = 'succeeded', locked_by = null, locked_until = null
       where id = any($1::uuid[])`,
      [createdJobIds],
    );
  });

  afterAll(async () => {
    await db.end();
  });

  it("gives concurrent workers different pending jobs", async () => {
    const firstJobId = await createReviewJob();
    const secondJobId = await createReviewJob();

    const [first, second] = await withOtherEligibleJobsLocked([firstJobId, secondJobId], () =>
      Promise.all([claimReviewJob("worker-a"), claimReviewJob("worker-b")]),
    );

    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(first?.id).not.toBe(second?.id);
    expect([first?.lockedBy, second?.lockedBy].sort()).toEqual(["worker-a", "worker-b"]);
    expect(first?.lockedUntil).toBeInstanceOf(Date);
    expect(second?.lockedUntil).toBeInstanceOf(Date);
  });

  it("reclaims a running job whose lease expired after a worker crash", async () => {
    const jobId = await createReviewJob();
    await db.query(
      `update review_jobs
       set status = 'running', attempts = 1, locked_by = 'crashed-worker', locked_until = now() - interval '1 second'
       where id = $1`,
      [jobId],
    );

    const claimed = await withOtherEligibleJobsLocked([jobId], () => claimReviewJob("replacement-worker"));

    expect(claimed).toMatchObject({
      id: jobId,
      status: "running",
      attempts: 2,
      lockedBy: "replacement-worker",
    });
  });

  it("skips a job row held by another transaction", async () => {
    const jobId = await createReviewJob();
    await withOtherEligibleJobsLocked([], async () => {
      await expect(claimReviewJob("worker-b")).resolves.toBeNull();
    });
  });

  it("rejects completion and failure from a worker that does not own the lease", async () => {
    await createReviewJob();
    const claimed = await withOtherEligibleJobsLocked(createdJobIds, () => claimReviewJob("worker-a"));

    if (claimed === null) {
      throw new Error("Expected a job to be claimed");
    }

    await expect(completeReviewJob(claimed.id, "worker-b")).rejects.toThrow();
    await expect(failReviewJob(claimed.id, "worker-b", "unexpected failure")).rejects.toThrow();

    const result = await db.query<{ status: string; locked_by: string }>(
      "select status, locked_by from review_jobs where id = $1",
      [claimed.id],
    );
    expect(result.rows[0]).toEqual({ status: "running", locked_by: "worker-a" });
  });

  it("retries a failed job three times before marking it failed", async () => {
    const jobId = await createReviewJob();

    await withOtherEligibleJobsLocked([jobId], async () => {
      for (const workerId of ["worker-1", "worker-2", "worker-3"]) {
        const claimed = await claimReviewJob(workerId);
        if (claimed === null) {
          throw new Error("Expected a job to be claimed");
        }

        await failReviewJob(claimed.id, workerId, `failure from ${workerId}`);
        await db.query("update review_jobs set available_at = now() where id = $1", [claimed.id]);
      }
    });

    const result = await db.query<{ status: string; attempts: number; last_error: string }>(
      "select status, attempts, last_error from review_jobs where id = $1",
      [jobId],
    );
    expect(result.rows).toEqual([
      { status: "failed", attempts: 3, last_error: "failure from worker-3" },
    ]);
  });

  it("renews the lease only for its owning worker", async () => {
    await createReviewJob();
    const claimed = await withOtherEligibleJobsLocked(createdJobIds, () => claimReviewJob("worker-a"));

    if (claimed === null) {
      throw new Error("Expected a job to be claimed");
    }

    await db.query("update review_jobs set locked_until = now() + interval '1 second' where id = $1", [claimed.id]);
    await expect(renewReviewJobLease(claimed.id, "worker-a")).resolves.toBeUndefined();
    await expect(renewReviewJobLease(claimed.id, "worker-b")).rejects.toThrow();

    const result = await db.query<{ locked_by: string; locked_until: Date }>(
      "select locked_by, locked_until from review_jobs where id = $1",
      [claimed.id],
    );
    expect(result.rows[0].locked_by).toBe("worker-a");
    expect(result.rows[0].locked_until.getTime()).toBeGreaterThan(Date.now() + 4 * 60 * 1000);
  });

  async function createReviewJob(): Promise<string> {
    deliveryNumber += 1;
    const deliveryId = `lease-delivery-${deliveryNumber}-${randomUUID()}`;
    await db.query("insert into github_deliveries (id, event_name) values ($1, 'pull_request')", [deliveryId]);
    const result = await db.query<{ id: string }>(
      "insert into review_jobs (delivery_id, status) values ($1, 'pending') returning id",
      [deliveryId],
    );
    const jobId = result.rows[0].id;
    createdJobIds.push(jobId);
    return jobId;
  }

  async function withOtherEligibleJobsLocked<T>(
    fixtureJobIds: string[],
    operation: () => Promise<T>,
  ): Promise<T> {
    const lockClient = await db.connect();

    try {
      await lockClient.query("begin");
      await lockClient.query(
        `select id
         from review_jobs
         where id <> all($1::uuid[])
           and (
             (status = 'pending' and available_at <= now())
             or (status = 'running' and locked_until <= now())
           )
         for update`,
        [fixtureJobIds],
      );
      return await operation();
    } finally {
      await lockClient.query("rollback");
      lockClient.release();
    }
  }
});
